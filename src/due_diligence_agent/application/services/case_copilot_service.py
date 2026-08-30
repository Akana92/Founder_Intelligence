from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, NamedTuple, TypedDict, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.application.case_copilot_contracts import (
    AcceptedInputProjection,
    ActionAvailabilityProjection,
    AssumptionOutcomeResponse,
    CaseMutationDeltaResponse,
    CaseQuestionDescriptorProjection,
    CopilotMessageResponse,
    CopilotStateResponse,
    CopilotThreadResponse,
    CoverageProjection,
    FactMutationResponse,
    FactPeriod,
    FactProjection,
    FieldErrorResponse,
    GapProjection,
    MoneyFactValue,
    PostCopilotMessageRequest,
    PrepareResearchPlanRequest,
    QueueResearchJobRequest,
    ResearchJobResponse,
    ResearchPlanResponse,
    SaveAssumptionRequest,
    SaveFounderFactRequest,
    ScenarioMetricProjection,
    ScenarioProjectionResponse,
    ScenarioSelectionResponse,
    SelectScenarioRequest,
    TextFactValue,
)
from due_diligence_agent.application.services.case_fact_intake_service import (
    CaseMutationDelta,
    SaveFounderStatementCommand,
)
from due_diligence_agent.application.services.case_question_service import (
    requirement_registry,
    resolve_case_stage,
)
from due_diligence_agent.application.services.case_research_job_service import (
    _normalize_live_public_research_snapshot,
)
from due_diligence_agent.application.services.startup_gtm_service import StartupGtmService
from due_diligence_agent.application.services.startup_product_validation_service import (
    StartupProductValidationService,
)
from due_diligence_agent.application.services.startup_readiness_service import (
    StartupReadinessService,
)
from due_diligence_agent.application.startup_cases import (
    StartupGateConflict,
    StartupNotFound,
    StartupValidationError,
)
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, CaseStatus, SensitivityClass
from due_diligence_agent.domain.startup.case_intake import (
    CaseStage,
    CaseValueKind,
    FounderStatement,
)
from due_diligence_agent.domain.startup.copilot import CopilotMessage, CopilotThread
from due_diligence_agent.domain.startup.gtm import StartupGtmSnapshot
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupPublicBenchmarkCandidate,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
)
from due_diligence_agent.domain.startup.readiness import (
    StartupMetricPack,
    StartupReadinessSnapshot,
)
from due_diligence_agent.domain.startup.roles import StartupProductValidationSnapshot
from due_diligence_agent.domain.startup.scenario import ScenarioInput

_SOURCE_STATUSES = {
    CaseValueKind.SOURCE_FACT: "confirmed",
    CaseValueKind.FOUNDER_STATEMENT: "provisional",
    CaseValueKind.PUBLIC_BENCHMARK: "external_context",
    CaseValueKind.DETERMINISTIC_CALCULATION: "calculated",
    CaseValueKind.AI_SCENARIO: "planning_assumption",
    CaseValueKind.CONTRADICTION: "conflict_open",
}
_REQUIREMENT_KEY_ALIASES = {
    "monthly_recurring_revenue": "mrr",
    "monthly_net_burn": "burn",
    "net_burn": "burn",
}


class _QuestionSelection(NamedTuple):
    descriptor: CaseQuestionDescriptorProjection | None
    prompt: str | None
_CANONICAL_ACTION_KEYS = (
    "open_fact_input",
    "open_document_upload",
    "prepare_public_research",
    "explain_metric",
    "navigate",
    "prepare_asset",
    "review_improvements",
)
_LAUNCH_PACK_MARKER_KEYS = (
    "product_validation_snapshot_id",
    "product_validation_snapshot_hash",
    "product_validation_snapshot_revision",
    "market_research_snapshot_id",
    "market_research_snapshot_hash",
    "market_research_snapshot_revision",
    "readiness_snapshot_id",
    "readiness_snapshot_hash",
    "readiness_snapshot_revision",
    "gtm_snapshot_id",
    "gtm_snapshot_hash",
    "gtm_snapshot_revision",
)


class ResearchAcquisitionModeCapability(TypedDict):
    available: tuple[str, ...]
    unavailable: tuple[str, ...]
    default: str


class CaseCopilotService:
    def __init__(
        self,
        *,
        workflow_store: Any,
        read_model_workflow_store: Any | None = None,
        inbox_root: Any,
        case_repository: Any,
        profile_repository: Any,
        assumption_repository: Any,
        thread_repository: Any,
        fact_intake_service: Any,
        question_service: Any,
        scenario_service: Any,
        scenario_repository: Any,
        research_service: Any | None = None,
        copilot_advice_provider: Any | None = None,
        public_benchmark_repository: Any | None = None,
        analysis_revision_starter: Callable[..., None] | None = None,
    ) -> None:
        self._workflow_store = workflow_store
        self._read_model_workflow_store = read_model_workflow_store or workflow_store
        self._inbox_root = inbox_root
        self._case_repository = case_repository
        self._profiles = profile_repository
        self._assumptions = assumption_repository
        self._threads = thread_repository
        self._fact_intake = fact_intake_service
        self._questions = question_service
        self._scenarios = scenario_service
        self._scenario_repository = scenario_repository
        self._research_service = research_service
        self._copilot_advice_provider = copilot_advice_provider
        self._public_benchmarks = public_benchmark_repository
        self._analysis_revision_starter = analysis_revision_starter

    def state(self, case_id: UUID) -> CopilotStateResponse:
        case = self._ensure_case(case_id)
        statements = self._statements(case_id)
        benchmark_inputs = self._accepted_public_benchmark_inputs(case_id)
        projection = self._same_case_projection(case)
        scenario_set = self._current_scenario_set(case)
        question_selection = self._question_selection(case, projection)
        return CopilotStateResponse(
            case_id=case_id,
            data_revision=case.data_revision,
            stage=_case_stage(self._questions, self._profiles, case.case_id).value,
            next_question=question_selection.prompt,
            question_descriptor=question_selection.descriptor,
            suggested_action="prepare_public_research",
            selected_scenario_key=scenario_set.selected_scenario_key,
            extracted_facts=projection.facts,
            prioritized_gaps=projection.gaps,
            scenario_metrics=_scenario_metrics_from_set(scenario_set),
            fact_coverage=CoverageProjection(
                measure="evidence-backed",
                status="partial",
                source_fact_count=sum(
                    1 for fact in projection.facts if fact.source_type is CaseValueKind.SOURCE_FACT
                ),
            ),
            scenario_completeness=CoverageProjection(
                measure="planning-model",
                status="draft",
                accepted_input_count=len(statements) + len(benchmark_inputs),
            ),
            accepted_inputs=[
                *_source_status_rows(),
                *[_accepted_input_from_statement(statement) for statement in statements],
                *[
                    _accepted_input_from_public_benchmark(benchmark)
                    for benchmark in benchmark_inputs
                ],
            ],
            actions=_typed_actions(
                case,
                projection,
                question_descriptor=question_selection.descriptor,
                acquisition_modes=self._research_acquisition_modes(),
            ),
        )

    def thread(self, case_id: UUID, *, thread_id: UUID | None = None) -> CopilotThreadResponse:
        case = self._ensure_case(case_id)
        if thread_id is not None:
            try:
                thread = self._threads.get_for_case(case_id, thread_id)
            except KeyError as exc:
                raise StartupNotFound("thread_not_found") from exc
            return CopilotThreadResponse.model_validate(thread.model_dump(mode="python"))
        try:
            thread = self._threads.get_current(case_id)
        except KeyError:
            thread = CopilotThread(
                thread_id=_thread_id(case_id),
                case_id=case_id,
                data_revision=case.data_revision,
                messages=(
                    CopilotMessage(
                        message_id=_message_id(case_id, case.data_revision, "system", "created"),
                        case_id=case_id,
                        data_revision=case.data_revision,
                        role="system_event",
                        content="Case Copilot is ready with same-case facts and scenario boundaries.",
                    ),
                ),
            )
            thread = self._threads.save(
                thread,
                expected_revision=case.data_revision,
                idempotency_key="thread:create",
            )
        return CopilotThreadResponse.model_validate(thread.model_dump(mode="python"))

    def post_message(
        self,
        case_id: UUID,
        request: PostCopilotMessageRequest,
    ) -> CopilotMessageResponse:
        sanitized_user_message = _sanitize_copilot_text(request.message)
        turn_fingerprint = _turn_fingerprint(request, sanitized_user_message)
        replay_thread = self._thread_by_idempotency(
            case_id,
            f"copilot-turn:{request.idempotency_key}",
        )
        if replay_thread is not None:
            replay_fingerprint = _last_turn_fingerprint(replay_thread)
            if replay_fingerprint != turn_fingerprint:
                raise StartupGateConflict("idempotency_key_conflict")
            case = self._ensure_case(case_id)
            replayed_user = next(
                (
                    message
                    for message in reversed(replay_thread.messages)
                    if message.role == "user"
                ),
                None,
            )
            replayed_assistant = next(
                (
                    message
                    for message in reversed(replay_thread.messages)
                    if message.role == "assistant"
                ),
                None,
            )
            if replayed_assistant is None:
                raise StartupGateConflict("copilot_action_snapshot_corrupt")
            replayed_message = replayed_assistant.content
            replayed_actions = _validated_actions_from_message(replayed_assistant)
            return CopilotMessageResponse(
                case_id=case_id,
                data_revision=replay_thread.data_revision,
                thread_id=replay_thread.thread_id,
                page_context=replayed_user.page_context if replayed_user is not None and replayed_user.page_context is not None else request.page_context,
                current_section=(
                    replayed_user.current_section
                    if replayed_user is not None and replayed_user.current_section is not None
                    else request.current_section
                ),
                status="accepted",
                message=replayed_message,
                available_actions=replayed_actions,
            )
        case = self._ensure_case(case_id)
        if case.data_revision != request.expected_case_revision:
            raise StartupGateConflict("case_revision_conflict")
        self._validate_runtime_revision_before_mutation(case_id, request.expected_case_revision)
        projection = self._same_case_projection(case)
        question_selection = self._question_selection(
            case,
            projection,
            page_context=request.page_context,
            focus_key=request.focus_key,
        )
        prompt = (
            question_selection.prompt
            or "Which founder-supplied evidence should be captured before changing the case model?"
        )
        actions = _typed_actions(
            case,
            projection,
            question_descriptor=question_selection.descriptor,
            acquisition_modes=self._research_acquisition_modes(),
        )
        assistant_message = self._advice_message(
            case,
            projection,
            prompt,
            page_context=request.page_context,
            current_section=request.current_section,
            focus_key=request.focus_key,
            fallback=_assistant_message(case, projection, prompt),
        )
        thread = self._append_copilot_turn(
            case,
            user_content=sanitized_user_message,
            assistant_content=assistant_message,
            page_context=request.page_context,
            current_section=request.current_section,
            actions=tuple(actions),
            idempotency_key=request.idempotency_key,
            idempotency_fingerprint=turn_fingerprint,
        )
        stored_assistant = next(
            (
                message
                for message in reversed(thread.messages)
                if message.role == "assistant"
            ),
            None,
        )
        response_message = stored_assistant.content if stored_assistant is not None else assistant_message
        return CopilotMessageResponse(
            case_id=case_id,
            data_revision=case.data_revision,
            thread_id=thread.thread_id,
            page_context=request.page_context,
            current_section=request.current_section,
            status="accepted",
            message=response_message,
            available_actions=actions,
        )

    def save_fact(self, case_id: UUID, request: SaveFounderFactRequest) -> FactMutationResponse:
        errors = _fact_validation_errors(request)
        if errors:
            raise _FactValidationFailure(errors)
        if request.source.kind is not CaseValueKind.FOUNDER_STATEMENT:
            raise StartupValidationError("fact_source_kind_not_supported")
        self._ensure_case(case_id)
        is_replay = _has_fact_idempotency(
            self._assumptions,
            case_id,
            request.idempotency_key,
        )
        if not is_replay:
            self._validate_runtime_revision_before_mutation(
                case_id,
                request.expected_case_revision,
            )
            self._preflight_profile_backed_read_model_projection(
                case_id,
                expected_revision=request.expected_case_revision,
            )
        delta = cast(
            CaseMutationDelta,
            self._fact_intake.save_founder_statement(_fact_command(case_id, request)),
        )
        if delta.accepted:
            self._sync_revision_read_models_after_commit(
                case_id,
                old_revision=delta.old_revision,
                new_revision=delta.new_revision,
                fail_closed_on_projection_conflict=is_replay,
            )
            self._append_system_event(
                case_id,
                data_revision=delta.new_revision,
                content=f"Saved founder_statement for {request.requirement_key}.",
                idempotency_key=f"fact-event:{request.idempotency_key}",
            )
        return FactMutationResponse(
            case_id=case_id,
            accepted=delta.accepted,
            provenance=CaseValueKind.FOUNDER_STATEMENT,
            source_type=CaseValueKind.FOUNDER_STATEMENT,
            old_revision=delta.old_revision,
            new_revision=delta.new_revision,
            changed_keys=delta.changed_keys,
            delta=_delta_response(delta),
        )

    def save_assumption(self, case_id: UUID, request: SaveAssumptionRequest) -> AssumptionOutcomeResponse:
        case = self._ensure_case(case_id)
        if request.source.kind is not CaseValueKind.FOUNDER_STATEMENT:
            return AssumptionOutcomeResponse(
                case_id=case_id,
                status="blocked",
                provenance=request.source.kind,
                reason=(
                    "Task 5 only lets explicit founder_statement assumptions mutate; "
                    f"{request.source.kind.value} is owned by the scenario/research service."
                ),
                old_revision=case.data_revision,
                new_revision=case.data_revision,
            )
        fact_request = SaveFounderFactRequest(
            requirement_key=request.requirement_key,
            value=request.value,
            period=request.period,
            source=request.source,
            note=request.rationale,
            expected_case_revision=request.expected_case_revision,
            idempotency_key=request.idempotency_key,
        )
        errors = _fact_validation_errors(fact_request)
        if errors:
            raise _FactValidationFailure(errors)
        is_replay = _has_fact_idempotency(
            self._assumptions,
            case_id,
            request.idempotency_key,
        )
        if not is_replay:
            self._validate_runtime_revision_before_mutation(
                case_id,
                request.expected_case_revision,
            )
            self._preflight_profile_backed_read_model_projection(
                case_id,
                expected_revision=request.expected_case_revision,
            )
        delta = cast(
            CaseMutationDelta,
            self._fact_intake.save_founder_statement(_assumption_command(case_id, request)),
        )
        if delta.accepted:
            self._sync_revision_read_models_after_commit(
                case_id,
                old_revision=delta.old_revision,
                new_revision=delta.new_revision,
                fail_closed_on_projection_conflict=is_replay,
            )
            self._append_system_event(
                case_id,
                data_revision=delta.new_revision,
                content=f"Saved founder_statement assumption for {request.requirement_key}.",
                idempotency_key=f"assumption-event:{request.idempotency_key}",
            )
        statement = _statement_by_idempotency(self._assumptions, case_id, request.idempotency_key)
        return AssumptionOutcomeResponse(
            case_id=case_id,
            status="accepted" if delta.accepted else "blocked",
            provenance=CaseValueKind.FOUNDER_STATEMENT,
            reason=None,
            old_revision=delta.old_revision,
            new_revision=delta.new_revision,
            delta=_delta_response(delta),
            accepted_input=_accepted_input_from_statement(statement) if statement is not None else None,
        )

    def scenarios(self, case_id: UUID) -> ScenarioProjectionResponse:
        case = self._ensure_case(case_id)
        scenario_set = self._current_scenario_set(case)
        return ScenarioProjectionResponse(
            scenario_set_id=scenario_set.scenario_set_id,
            case_id=scenario_set.case_id,
            data_revision=scenario_set.data_revision,
            selected_scenario_key=scenario_set.selected_scenario_key,
            scenarios=scenario_set.scenarios,
            fact_coverage=CoverageProjection(measure="evidence-backed", status="partial"),
            scenario_completeness=CoverageProjection(measure="planning-model", status="draft"),
        )

    def select_scenario(self, case_id: UUID, request: SelectScenarioRequest) -> ScenarioSelectionResponse:
        case = self._ensure_case(case_id)
        try:
            current = self._scenario_repository.get_current(case_id)
        except KeyError:
            current = self._scenarios.build(
                case_id,
                expected_case_revision=case.data_revision,
                idempotency_key=f"scenario-build:{case.data_revision}",
            )
        if current.data_revision != case.data_revision:
            current = self._scenarios.build(
                case_id,
                expected_case_revision=case.data_revision,
                idempotency_key=f"scenario-build:{case.data_revision}",
            )
        if request.scenario_set_id is not None and request.scenario_set_id != current.scenario_set_id:
            raise StartupNotFound("scenario_set_not_found")
        delta = self._scenarios.select(
            case_id,
            request.scenario_key,
            expected_case_revision=request.expected_case_revision,
            idempotency_key=request.idempotency_key,
        )
        return ScenarioSelectionResponse.model_validate(delta.model_dump(mode="python"))

    def prepare_research_plan(self, case_id: UUID, request: PrepareResearchPlanRequest) -> ResearchPlanResponse:
        if self._research_service is None:
            raise StartupValidationError("research_service_unavailable")
        return cast(ResearchPlanResponse, self._research_service.prepare_plan(case_id, request))

    def queue_research_job(self, case_id: UUID, request: QueueResearchJobRequest) -> ResearchJobResponse:
        if self._research_service is None:
            raise StartupValidationError("research_service_unavailable")
        case = self._ensure_case(case_id)
        if request.consent_public_research and request.expected_case_revision == case.data_revision:
            runtime = self._workflow_store.load(str(case_id))
            if _runtime_has_profile_projection(runtime):
                self._preflight_profile_backed_read_model_projection(
                    case_id,
                    expected_revision=request.expected_case_revision,
                    runtime=runtime,
                )
        response = cast(ResearchJobResponse, self._research_service.queue_job(case_id, request))
        self._sync_public_research_read_models(
            case_id,
            response,
            idempotency_key=request.idempotency_key,
            is_replay=request.expected_case_revision < case.data_revision,
        )
        return response

    def research_job(self, case_id: UUID, job_id: UUID) -> ResearchJobResponse:
        if self._research_service is None:
            raise StartupValidationError("research_service_unavailable")
        return cast(ResearchJobResponse, self._research_service.get_job(case_id, job_id))

    def _research_acquisition_modes(self) -> ResearchAcquisitionModeCapability:
        default: ResearchAcquisitionModeCapability = {
            "available": (),
            "unavailable": ("live_public_research", "deterministic_offline_fixture"),
            "default": "live_public_research",
        }
        if self._research_service is None:
            return default
        capability = getattr(self._research_service, "available_acquisition_modes", None)
        if not callable(capability):
            return default
        result = capability()
        return cast(ResearchAcquisitionModeCapability, result) if isinstance(result, dict) else default

    def _statements(self, case_id: UUID) -> tuple[FounderStatement, ...]:
        try:
            return tuple(self._assumptions.get_current(case_id))
        except (KeyError, ValueError):
            return ()

    def _accepted_public_benchmark_inputs(self, case_id: UUID) -> tuple[ScenarioInput, ...]:
        if self._public_benchmarks is None:
            return ()
        try:
            inputs = tuple(self._public_benchmarks.get_current(case_id))
        except (KeyError, ValueError):
            return ()
        selected: dict[str, ScenarioInput] = {}
        for item in sorted(inputs, key=lambda value: (value.data_revision or 0, str(value.input_id))):
            if item.case_id != case_id:
                continue
            if item.provenance is not CaseValueKind.PUBLIC_BENCHMARK:
                continue
            if item.acceptance != "accepted":
                continue
            if not item.source_refs:
                continue
            selected[_normalize_key(item.input_key)] = item
        return tuple(selected[key] for key in sorted(selected))

    def _sync_public_research_read_models(
        self,
        case_id: UUID,
        response: ResearchJobResponse,
        *,
        idempotency_key: str,
        is_replay: bool = False,
    ) -> None:
        if response.status not in {"completed", "partial"}:
            return
        old_revision = response.old_revision
        new_revision = response.new_revision
        if type(old_revision) is not int or type(new_revision) is not int:
            raise StartupGateConflict("research_revision_unavailable")
        if new_revision <= old_revision:
            return
        self._materialize_public_research_market_artifact(
            case_id,
            response,
            new_revision=new_revision,
        )
        self._sync_revision_read_models_after_commit(
            case_id,
            old_revision=old_revision,
            new_revision=new_revision,
            fail_closed_on_projection_conflict=is_replay,
        )
        if "scenarios" in response.changed_blocks:
            case = self._ensure_case(case_id)
            if case.data_revision != new_revision:
                raise StartupGateConflict("research_revision_unavailable")
            scenario_set = self._current_scenario_set(case)
            if scenario_set.data_revision != new_revision:
                raise StartupGateConflict("research_scenario_projection_unavailable")
        self._append_system_event(
            case_id,
            data_revision=new_revision,
            content="Accepted public_benchmark research updated scenario context.",
            idempotency_key=f"research-event:{idempotency_key}:{new_revision}",
        )

    def _materialize_public_research_market_artifact(
        self,
        case_id: UUID,
        response: ResearchJobResponse,
        *,
        new_revision: int,
    ) -> None:
        if response.acquisition_mode != "live_public_research":
            return
        persisted_snapshot = self._persisted_public_research_market_snapshot(
            case_id,
            response,
            new_revision=new_revision,
        )
        if persisted_snapshot is not None:
            update = _market_research_projection_update(persisted_snapshot)
            self._read_model_workflow_store.update(
                str(case_id),
                lambda runtime: {
                    **runtime,
                    **update,
                },
            )
            return
        if not response.accepted_entries:
            return
        runtime = self._read_model_runtime(case_id)
        previous: StartupMarketResearchSnapshot | None = None
        raw_artifact = runtime.get("startup_market_research_artifact")
        if isinstance(raw_artifact, dict):
            try:
                previous = StartupMarketResearchSnapshot.model_validate(raw_artifact["snapshot"])
            except (KeyError, TypeError, ValueError) as exc:
                raise StartupGateConflict("research_profile_projection_unavailable") from exc
            if previous.case_id != case_id:
                raise StartupGateConflict("research_profile_projection_unavailable")
        sources: dict[UUID, StartupResearchSource] = {
            source.source_id: source
            for source in previous.sources
        } if previous is not None else {}
        candidates: dict[tuple[str, str], StartupPublicBenchmarkCandidate] = {
            (candidate.input_key, candidate.source_url): candidate
            for candidate in previous.public_benchmark_candidates
        } if previous is not None else {}
        for entry in response.accepted_entries:
            source_id = _public_research_source_id(entry.source_refs, entry.url)
            source_as_of = _date_from_iso(entry.as_of)
            retrieved_at = _datetime_from_iso_date(entry.retrieval_date)
            source_url = entry.url.rstrip("/") if entry.url.endswith("/") else entry.url
            sources[source_id] = StartupResearchSource.model_validate(
                {
                    "source_id": source_id,
                    "source_mode": StartupResearchSourceMode.LIVE,
                    "source_hash": _public_research_source_hash(
                        entry.url,
                        entry.publisher,
                        entry.retrieval_date,
                    ),
                    "source_url": entry.url,
                    "source_label": entry.publisher,
                    "as_of": source_as_of,
                    "retrieved_at": retrieved_at,
                    "query": f"accepted public benchmark: {entry.input_key}",
                    "provenance": "public_benchmark",
                    "confidence": _public_research_confidence(entry.confidence),
                    "supports_primary_financial_metrics": False,
                    "status": StartupResearchSourceStatus.INFERENCE,
                }
            )
            candidate = StartupPublicBenchmarkCandidate.model_validate(
                {
                    "input_key": entry.input_key,
                    "source_url": source_url,
                    "publisher": entry.publisher,
                    "publication_date": entry.publication_date,
                    "retrieval_date": entry.retrieval_date,
                    "as_of": entry.as_of,
                    "source_class": entry.source_class,
                    "confidence": entry.confidence,
                    "value": entry.value,
                    "range_low": entry.range.get("low"),
                    "range_high": entry.range.get("high"),
                    "unit": entry.unit,
                    "period": entry.period,
                    "formula": entry.formula,
                    "dependencies": tuple(entry.dependencies),
                    "validation_plan": entry.validation_plan,
                    "source_ref": source_id,
                    "rationale": entry.formula,
                }
            )
            candidates[(candidate.input_key, candidate.source_url)] = candidate
        raw_snapshot = StartupMarketResearchSnapshot.build(
            case_id=case_id,
            as_of=previous.as_of if previous is not None else response.updated_at,
            source_mode=StartupResearchSourceMode.LIVE,
            research_id=previous.research_id if previous is not None else response.job_id,
            competitors=previous.competitors if previous is not None else (),
            sources=tuple(sources.values()),
            sentiment_signals=previous.sentiment_signals if previous is not None else (),
            assumptions=previous.assumptions if previous is not None else (),
            sizing=previous.sizing if previous is not None else None,
            labels=(
                *(previous.labels if previous is not None else ()),
                "live_public_research",
                "public_benchmark",
            ),
            data_revision=new_revision,
            public_benchmark_candidates=tuple(candidates.values()),
        )
        snapshot = _normalize_live_public_research_snapshot(
            raw_snapshot,
            case_id=case_id,
            data_revision=new_revision,
        )
        update = _market_research_projection_update(snapshot)
        self._read_model_workflow_store.update(
            str(case_id),
            lambda runtime: {
                **runtime,
                **update,
            },
        )

    def _persisted_public_research_market_snapshot(
        self,
        case_id: UUID,
        response: ResearchJobResponse,
        *,
        new_revision: int,
    ) -> StartupMarketResearchSnapshot | None:
        getter = getattr(self._research_service, "get_internal_job", None)
        if not callable(getter):
            return None
        try:
            job = getter(case_id, response.job_id)
        except Exception as exc:
            raise StartupGateConflict("research_job_snapshot_unavailable") from exc
        snapshot = getattr(job, "live_market_research_snapshot", None)
        if not isinstance(snapshot, StartupMarketResearchSnapshot):
            return None
        return _normalize_live_public_research_snapshot(
            snapshot,
            case_id=case_id,
            data_revision=new_revision,
        )

    def _sync_revision_read_models_after_commit(
        self,
        case_id: UUID,
        *,
        old_revision: int,
        new_revision: int,
        fail_closed_on_projection_conflict: bool = False,
    ) -> None:
        last_conflict: StartupGateConflict | None = None
        projection_succeeded = False
        for _attempt in range(2):
            try:
                self._sync_revision_read_models(
                    case_id,
                    old_revision=old_revision,
                    new_revision=new_revision,
                )
            except StartupGateConflict as exc:
                last_conflict = exc
                continue
            projection_succeeded = True
            break
        if not projection_succeeded:
            if fail_closed_on_projection_conflict and last_conflict is not None:
                raise last_conflict
            self._invalidate_launch_pack_markers_after_projection_failure(
                case_id,
                data_revision=new_revision,
            )
            return
        self._seed_projected_analysis_revision(case_id, data_revision=new_revision)
        try:
            self._sync_revision_read_models(
                case_id,
                old_revision=old_revision,
                new_revision=new_revision,
            )
        except StartupGateConflict:
            if fail_closed_on_projection_conflict:
                raise
            self._invalidate_launch_pack_markers_after_projection_failure(
                case_id,
                data_revision=new_revision,
            )

    def _seed_projected_analysis_revision(
        self,
        case_id: UUID,
        *,
        data_revision: int,
    ) -> None:
        runtime = self._workflow_store.load(str(case_id))
        thread_id = f"{case_id}:r{data_revision}"
        if (
            runtime.get("analysis_status") not in {"gate2_preview_ready", "failed"}
            or runtime.get("active_analysis_thread_id") != thread_id
            or runtime.get("data_revision") != data_revision
            or (
                runtime.get("analysis_status") == "failed"
                and runtime.get("analysis_revision_seed_status") != "retryable"
            )
        ):
            return
        payload = _startup_analysis_revision_payload(
            case_id,
            runtime=runtime,
            data_revision=data_revision,
        )
        if payload is None:
            self._mark_analysis_revision_seed_unavailable(
                case_id,
                data_revision=data_revision,
                thread_id=thread_id,
                error_code="analysis_revision_seed_payload_invalid",
            )
            return
        try:
            self._start_startup_analysis_revision(payload, thread_id=thread_id)
        except StartupGateConflict as exc:
            if exc.code != "analysis_revision_starter_unavailable":
                raise
            self._mark_analysis_revision_seed_unavailable(
                case_id,
                data_revision=data_revision,
                thread_id=thread_id,
                error_code=exc.code,
            )

    def _mark_analysis_revision_seed_unavailable(
        self,
        case_id: UUID,
        *,
        data_revision: int,
        thread_id: str,
        error_code: str,
    ) -> None:
        def mark_failed(runtime: dict[str, Any]) -> dict[str, Any]:
            if (
                runtime.get("data_revision") != data_revision
                or runtime.get("active_analysis_thread_id") != thread_id
                or runtime.get("analysis_revision_seed_status") not in {"pending", "retryable"}
            ):
                return {}
            return {
                "analysis_status": "failed",
                "gate2_status": "not_ready",
                "gate2_preview": None,
                "gate2_resume_token_digest": None,
                "gate2_resume_token_used": False,
                "analysis_revision_seed_required": True,
                "analysis_revision_seed_status": "retryable",
                "error_code": error_code,
            }

        self._workflow_store.update(str(case_id), mark_failed)

    def _invalidate_launch_pack_markers_after_projection_failure(
        self,
        case_id: UUID,
        *,
        data_revision: int,
    ) -> None:
        marker_reset = {key: None for key in _LAUNCH_PACK_MARKER_KEYS}
        self._workflow_store.update(
            str(case_id),
            lambda runtime: {
                **runtime,
                "data_revision": data_revision,
                **marker_reset,
            },
        )
        self._read_model_workflow_store.update(
            str(case_id),
            lambda runtime: {
                **runtime,
                "data_revision": data_revision,
                **marker_reset,
            },
        )

    def _sync_revision_read_models(
        self,
        case_id: UUID,
        *,
        old_revision: int,
        new_revision: int,
    ) -> None:
        if new_revision <= old_revision:
            return
        runtime = self._workflow_store.load(str(case_id))
        if _runtime_has_profile_projection(runtime):
            if _profile_projection_matches_revision(runtime, new_revision):
                current = self._runtime_profile_for_revision(
                    case_id,
                    runtime,
                    new_revision,
                )
                self._validate_runtime_profile_projection(
                    runtime,
                    current,
                    new_revision,
                )
                self._validate_repository_current_profile(case_id, current)
                read_model_runtime = self._read_model_runtime(case_id)
                try:
                    read_model_update = self._project_launch_pack_read_models(
                        read_model_runtime,
                        case_id=case_id,
                        profile=current,
                        new_revision=new_revision,
                    )
                except StartupGateConflict:
                    read_model_update = {}
                    self._invalidate_launch_pack_markers_after_projection_failure(
                        case_id,
                        data_revision=new_revision,
                    )
                if read_model_update:
                    profile_marker_update = _profile_marker_update(runtime)
                    self._read_model_workflow_store.update(
                        str(case_id),
                        lambda runtime: {
                            **runtime,
                            "data_revision": new_revision,
                            **profile_marker_update,
                            **read_model_update,
                        },
                    )
                    self._workflow_store.update(
                        str(case_id),
                        lambda runtime: {
                            **runtime,
                            **_launch_pack_marker_update(read_model_update),
                        },
                    )
            else:
                previous = self._runtime_profile_for_revision(
                    case_id,
                    {**runtime, "data_revision": old_revision},
                    old_revision,
                )
                self._validate_runtime_profile_transition(
                    runtime,
                    previous,
                    old_revision=old_revision,
                    new_revision=new_revision,
                )
                profile_update = self._project_profile_revision(
                    case_id,
                    previous=previous,
                    new_revision=new_revision,
                )
                projected_profile = self._profile_by_id(UUID(profile_update["profile_id"]))
                launch_pack_marker_update: dict[str, Any] = _launch_pack_marker_reset()
                try:
                    read_model_runtime = self._read_model_runtime(case_id)
                    read_model_update = self._project_launch_pack_read_models(
                        read_model_runtime,
                        case_id=case_id,
                        profile=projected_profile,
                        new_revision=new_revision,
                    )
                except StartupGateConflict:
                    read_model_update = {}
                    self._read_model_workflow_store.update(
                        str(case_id),
                        lambda runtime: {
                            **runtime,
                            "data_revision": new_revision,
                            **profile_update,
                            **launch_pack_marker_update,
                        },
                    )
                else:
                    launch_pack_marker_update = _launch_pack_marker_update(read_model_update)
                if read_model_update:
                    self._read_model_workflow_store.update(
                        str(case_id),
                        lambda runtime: {
                            **runtime,
                            "data_revision": new_revision,
                            **profile_update,
                            **read_model_update,
                        },
                    )
                self._workflow_store.update(
                    str(case_id),
                    lambda runtime: {
                        **runtime,
                        "data_revision": new_revision,
                        "analysis_status": "gate2_preview_ready",
                        "gate2_status": "not_ready",
                        "gate2_preview": None,
                        "gate2_resume_token_digest": None,
                        "gate2_resume_token_used": False,
                        "active_analysis_thread_id": f"{case_id}:r{new_revision}",
                        "analysis_start_claim_data_revision": new_revision,
                        "analysis_start_claim_thread_id": f"{case_id}:r{new_revision}",
                        "source_refs_revision": new_revision,
                        "source_ref_resolution_status": "resolved",
                        "analysis_revision_seed_required": True,
                        "analysis_revision_seed_status": "pending",
                        **profile_update,
                        **launch_pack_marker_update,
                    },
                )
        elif not _runtime_has_profile_projection(runtime):
            self._workflow_store.update(
                str(case_id),
                lambda runtime: {
                    **runtime,
                    "data_revision": new_revision,
                },
            )

    def _start_startup_analysis_revision(self, payload: dict[str, Any], *, thread_id: str) -> None:
        if self._analysis_revision_starter is None:
            raise StartupGateConflict("analysis_revision_starter_unavailable")
        self._analysis_revision_starter(payload, thread_id=thread_id)

    def _preflight_profile_backed_read_model_projection(
        self,
        case_id: UUID,
        *,
        expected_revision: int,
        runtime: dict[str, Any] | None = None,
    ) -> None:
        runtime = runtime or self._workflow_store.load(str(case_id))
        if not _runtime_has_profile_projection(runtime):
            return
        profile = self._runtime_profile_for_revision(case_id, runtime, expected_revision)
        self._validate_runtime_profile_projection(runtime, profile, expected_revision)
        self._validate_repository_current_profile_for_preflight(case_id, profile)
        read_model_runtime = self._read_model_runtime(case_id)
        self._validate_launch_pack_projection_inputs(
            case_id,
            runtime=runtime,
            read_model_runtime=read_model_runtime,
            profile=profile,
            expected_revision=expected_revision,
        )

    def _validate_launch_pack_projection_inputs(
        self,
        case_id: UUID,
        *,
        runtime: dict[str, Any],
        read_model_runtime: dict[str, Any],
        profile: StartupProfile,
        expected_revision: int,
    ) -> None:
        self._validate_launch_pack_runtime_consistency(
            runtime,
            read_model_runtime=read_model_runtime,
        )
        if not _runtime_has_launch_pack_projection(read_model_runtime):
            return
        read_model_revision = read_model_runtime.get("data_revision")
        if read_model_revision not in {None, expected_revision}:
            raise StartupGateConflict("research_profile_projection_unavailable")
        self._validate_launch_pack_artifacts(
            case_id,
            read_model_runtime,
            expected_revision=expected_revision,
        )
        self._project_launch_pack_read_models(
            read_model_runtime,
            case_id=case_id,
            profile=profile,
            new_revision=expected_revision,
        )

    def _validate_launch_pack_runtime_consistency(
        self,
        runtime: dict[str, Any],
        *,
        read_model_runtime: dict[str, Any],
    ) -> None:
        if not _runtime_has_launch_pack_projection(runtime):
            return
        if not _runtime_has_launch_pack_projection(read_model_runtime):
            raise StartupGateConflict("research_profile_projection_unavailable")
        for key in _LAUNCH_PACK_MARKER_KEYS:
            runtime_value = runtime.get(key)
            read_model_value = read_model_runtime.get(key)
            if runtime_value is not None and read_model_value is not None and runtime_value != read_model_value:
                raise StartupGateConflict("research_profile_projection_unavailable")
        for key in (
            "startup_product_validation_artifact",
            "startup_market_research_artifact",
            "startup_readiness_artifact",
            "startup_gtm_artifact",
        ):
            if key in runtime and key not in read_model_runtime:
                raise StartupGateConflict("research_profile_projection_unavailable")

    def _validate_launch_pack_artifacts(
        self,
        case_id: UUID,
        runtime: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        self._validate_product_validation_artifact(runtime, expected_revision=expected_revision)
        self._validate_market_research_artifact(
            case_id,
            runtime,
            expected_revision=expected_revision,
        )
        self._validate_readiness_artifact(runtime, expected_revision=expected_revision)
        self._validate_gtm_artifact(
            case_id,
            runtime,
            expected_revision=expected_revision,
        )

    def _validate_product_validation_artifact(
        self,
        runtime: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        raw_artifact = runtime.get("startup_product_validation_artifact")
        if raw_artifact is None:
            return
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            snapshot = StartupProductValidationSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        self._validate_snapshot_markers(
            runtime,
            marker_prefix="product_validation_snapshot",
            snapshot_id=str(snapshot.snapshot_id),
            snapshot_hash=snapshot.snapshot_hash,
            snapshot_revision=snapshot.profile_revision,
            expected_revision=expected_revision,
        )

    def _validate_market_research_artifact(
        self,
        case_id: UUID,
        runtime: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        raw_artifact = runtime.get("startup_market_research_artifact")
        if raw_artifact is None:
            return
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            snapshot = StartupMarketResearchSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if snapshot.case_id != case_id:
            raise StartupGateConflict("research_profile_projection_unavailable")
        self._validate_snapshot_markers(
            runtime,
            marker_prefix="market_research_snapshot",
            snapshot_id=str(snapshot.snapshot_id),
            snapshot_hash=snapshot.snapshot_hash,
            snapshot_revision=snapshot.data_revision,
            expected_revision=expected_revision,
        )

    def _validate_readiness_artifact(
        self,
        runtime: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        raw_artifact = runtime.get("startup_readiness_artifact")
        if raw_artifact is None:
            return
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            snapshot = StartupReadinessSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        self._validate_snapshot_markers(
            runtime,
            marker_prefix="readiness_snapshot",
            snapshot_id=str(snapshot.snapshot_id),
            snapshot_hash=snapshot.snapshot_hash,
            snapshot_revision=snapshot.profile_revision,
            expected_revision=expected_revision,
        )

    def _validate_gtm_artifact(
        self,
        case_id: UUID,
        runtime: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        raw_artifact = runtime.get("startup_gtm_artifact")
        if raw_artifact is None:
            return
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            snapshot = StartupGtmSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if snapshot.case_id != case_id:
            raise StartupGateConflict("research_profile_projection_unavailable")
        self._validate_snapshot_markers(
            runtime,
            marker_prefix="gtm_snapshot",
            snapshot_id=str(snapshot.snapshot_id),
            snapshot_hash=snapshot.snapshot_hash,
            snapshot_revision=snapshot.data_revision,
            expected_revision=expected_revision,
        )
        if runtime.get("product_validation_snapshot_id") != str(
            snapshot.product_validation_snapshot_id
        ) or runtime.get("market_research_snapshot_id") != str(
            snapshot.market_research_snapshot_id
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")

    def _validate_snapshot_markers(
        self,
        runtime: dict[str, Any],
        *,
        marker_prefix: str,
        snapshot_id: str,
        snapshot_hash: str,
        snapshot_revision: int,
        expected_revision: int,
    ) -> None:
        if (
            runtime.get(f"{marker_prefix}_id") != snapshot_id
            or runtime.get(f"{marker_prefix}_hash") != snapshot_hash
            or runtime.get(f"{marker_prefix}_revision") != snapshot_revision
            or snapshot_revision != expected_revision
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")

    def _runtime_profile_for_revision(
        self,
        case_id: UUID,
        runtime: dict[str, Any],
        data_revision: int,
    ) -> StartupProfile:
        profile_id = runtime.get("profile_id")
        if not isinstance(profile_id, str):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            profile = self._profiles.get(UUID(profile_id))
        except (AttributeError, KeyError, LookupError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if not isinstance(profile, StartupProfile):
            raise StartupGateConflict("research_profile_projection_unavailable")
        if profile.analysis_stage not in {
            StartupProfileAnalysisStage.PRIMARY,
            StartupProfileAnalysisStage.ENRICHED,
        }:
            raise StartupGateConflict("research_profile_projection_unavailable")
        if profile.case_id != case_id:
            raise StartupGateConflict("research_profile_projection_unavailable")
        self._validate_runtime_profile_projection(runtime, profile, data_revision)
        return profile

    def _read_model_runtime(self, case_id: UUID) -> dict[str, Any]:
        runtime = self._read_model_workflow_store.load(str(case_id))
        if not isinstance(runtime, dict):
            return {}
        return runtime

    def _primary_profile_for_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> StartupProfile:
        getter = getattr(self._profiles, "get_for_stage", None)
        if not callable(getter):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            profile = getter(case_id, data_revision, StartupProfileAnalysisStage.PRIMARY)
        except (KeyError, LookupError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if not isinstance(profile, StartupProfile):
            raise StartupGateConflict("research_profile_projection_unavailable")
        if (
            profile.case_id != case_id
            or profile.data_revision != data_revision
            or profile.analysis_stage is not StartupProfileAnalysisStage.PRIMARY
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")
        return profile

    def _project_profile_revision(
        self,
        case_id: UUID,
        *,
        previous: StartupProfile,
        new_revision: int,
    ) -> dict[str, Any]:
        if previous.case_id != case_id:
            raise StartupGateConflict("research_profile_projection_unavailable")
        if previous.analysis_stage is StartupProfileAnalysisStage.PRIMARY:
            profile = self._project_one_profile_revision(
                case_id,
                previous=previous,
                new_revision=new_revision,
                parent_profile_id=None,
            )
            return _profile_projection_update(profile)
        if previous.analysis_stage is not StartupProfileAnalysisStage.ENRICHED:
            raise StartupGateConflict("research_profile_projection_unavailable")
        old_primary = self._profile_by_id(previous.parent_profile_id)
        if (
            old_primary.case_id != case_id
            or old_primary.data_revision != previous.data_revision
            or old_primary.analysis_stage is not StartupProfileAnalysisStage.PRIMARY
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")
        new_primary = self._project_one_profile_revision(
            case_id,
            previous=old_primary,
            new_revision=new_revision,
            parent_profile_id=None,
        )
        new_enriched = self._project_one_profile_revision(
            case_id,
            previous=previous,
            new_revision=new_revision,
            parent_profile_id=new_primary.profile_id,
        )
        return _profile_projection_update(new_enriched, primary_profile=new_primary)

    def _project_one_profile_revision(
        self,
        case_id: UUID,
        *,
        previous: StartupProfile,
        new_revision: int,
        parent_profile_id: UUID | None,
    ) -> StartupProfile:
        if previous.case_id != case_id:
            raise StartupGateConflict("research_profile_projection_unavailable")
        existing = self._maybe_profile_for_revision(
            case_id,
            new_revision,
            previous.analysis_stage,
        )
        if existing is not None:
            if (
                existing.parent_profile_id != parent_profile_id
                or not _pending_profile_projection_matches(existing, previous)
            ):
                raise StartupGateConflict("research_profile_projection_unavailable")
            return existing
        profile = StartupProfile.build(
            case_id=case_id,
            schema_version=previous.schema_version,
            profile_version=previous.profile_version,
            extractor_version=previous.extractor_version,
            analysis_stage=previous.analysis_stage,
            parent_profile_id=parent_profile_id,
            data_revision=new_revision,
            source_hashes=previous.source_hashes,
            parse_outcomes=previous.parse_outcomes,
            fields=previous.fields,
            gap_codes=previous.gap_codes,
            contradiction_ids=previous.contradiction_ids,
            case_revision_at=datetime.now(UTC),
        )
        self._profiles.add(profile)
        return profile

    def _project_launch_pack_read_models(
        self,
        runtime: dict[str, Any],
        *,
        case_id: UUID,
        profile: StartupProfile,
        new_revision: int,
    ) -> dict[str, Any]:
        product_validation = self._project_product_validation_read_model(
            runtime,
            profile=profile,
        )
        market_research = self._project_market_research_read_model(
            runtime,
            case_id=case_id,
            new_revision=new_revision,
        )
        readiness = self._project_readiness_read_model(
            runtime,
            profile=profile,
        )
        update: dict[str, Any] = {}
        if product_validation is not None:
            update.update(
                _product_validation_projection_update(
                    runtime,
                    product_validation,
                )
            )
        if market_research is not None:
            update.update(_market_research_projection_update(market_research))
        if readiness is not None:
            update.update(_readiness_projection_update(readiness))
        if product_validation is not None and market_research is not None:
            gtm = self._project_gtm_read_model(
                runtime,
                profile=profile,
                product_validation=product_validation,
                market_research=market_research,
            )
            if gtm is not None:
                update.update(_gtm_projection_update(runtime, gtm))
        elif _runtime_has_gtm_projection(runtime):
            raise StartupGateConflict("research_profile_projection_unavailable")
        return update

    def _project_product_validation_read_model(
        self,
        runtime: dict[str, Any],
        *,
        profile: StartupProfile,
    ) -> StartupProductValidationSnapshot | None:
        raw_artifact = runtime.get("startup_product_validation_artifact")
        if raw_artifact is None:
            return None
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            StartupProductValidationSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        return StartupProductValidationService().evaluate(
            profile,
            evidence_fact_ids=_runtime_string_refs(runtime.get("evidence_fact_ids")),
            startup_claim_ids=_runtime_string_refs(runtime.get("startup_claim_ids")),
            claim_status_by_id=_runtime_string_mapping(runtime.get("claim_status_by_id")),
            contradiction_ids=_runtime_string_refs(runtime.get("contradiction_ids")),
        )

    def _project_market_research_read_model(
        self,
        runtime: dict[str, Any],
        *,
        case_id: UUID,
        new_revision: int,
    ) -> StartupMarketResearchSnapshot | None:
        raw_artifact = runtime.get("startup_market_research_artifact")
        if raw_artifact is None:
            return None
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            previous = StartupMarketResearchSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if previous.case_id != case_id:
            raise StartupGateConflict("research_profile_projection_unavailable")
        return StartupMarketResearchSnapshot.build(
            case_id=case_id,
            as_of=previous.as_of,
            source_mode=previous.source_mode,
            research_id=previous.research_id,
            competitors=previous.competitors,
            sources=previous.sources,
            sentiment_signals=previous.sentiment_signals,
            assumptions=previous.assumptions,
            sizing=previous.sizing,
            labels=previous.labels,
            data_revision=new_revision,
            public_benchmark_candidates=previous.public_benchmark_candidates,
        )

    def _project_readiness_read_model(
        self,
        runtime: dict[str, Any],
        *,
        profile: StartupProfile,
    ) -> StartupReadinessSnapshot | None:
        raw_artifact = runtime.get("startup_readiness_artifact")
        if raw_artifact is None:
            return None
        if not isinstance(raw_artifact, dict):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            StartupReadinessSnapshot.model_validate(raw_artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        service = StartupReadinessService(clock=lambda: profile.built_at)
        snapshot = service.evaluate(
            profile,
            runtime.get("metric_diagnostics", []),
            calculation_ids=tuple(
                UUID(item)
                for item in _runtime_string_refs(runtime.get("calculation_ids"))
            ),
        )
        questions = service.priority_questions(snapshot)
        if not questions:
            return snapshot
        pack = StartupMetricPack.build(
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
            metric_ids=snapshot.metric_pack.metric_ids,
            dimensions=snapshot.metric_pack.dimensions,
            adaptive_questions=questions,
            built_at=snapshot.built_at,
        )
        return StartupReadinessSnapshot.build(
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            profile_revision=profile.data_revision,
            metric_pack=pack,
            calculation_ids=snapshot.calculation_ids,
            diagnostic_ids=snapshot.diagnostic_ids,
            built_at=snapshot.built_at,
        )

    def _project_gtm_read_model(
        self,
        runtime: dict[str, Any],
        *,
        profile: StartupProfile,
        product_validation: StartupProductValidationSnapshot,
        market_research: StartupMarketResearchSnapshot,
    ) -> Any | None:
        if not _runtime_has_gtm_projection(runtime):
            return None
        return StartupGtmService().evaluate(
            profile,
            product_validation=product_validation,
            market_research=market_research,
            evidence_fact_ids=_runtime_string_refs(runtime.get("evidence_fact_ids")),
            finding_ids=_runtime_string_refs(runtime.get("finding_ids")),
            contradiction_ids=_runtime_string_refs(runtime.get("contradiction_ids")),
        )

    def _maybe_profile_for_revision(
        self,
        case_id: UUID,
        data_revision: int,
        stage: StartupProfileAnalysisStage,
    ) -> StartupProfile | None:
        getter = getattr(self._profiles, "get_for_stage", None)
        if not callable(getter):
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            profile = getter(case_id, data_revision, stage)
        except (KeyError, LookupError):
            return None
        except ValueError as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if not isinstance(profile, StartupProfile):
            raise StartupGateConflict("research_profile_projection_unavailable")
        if (
            profile.case_id != case_id
            or profile.data_revision != data_revision
            or profile.analysis_stage is not stage
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")
        return profile

    def _profile_by_id(self, profile_id: UUID | None) -> StartupProfile:
        if profile_id is None:
            raise StartupGateConflict("research_profile_projection_unavailable")
        try:
            profile = self._profiles.get(profile_id)
        except (AttributeError, KeyError, LookupError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if not isinstance(profile, StartupProfile):
            raise StartupGateConflict("research_profile_projection_unavailable")
        return profile

    def _validate_repository_current_profile(
        self,
        case_id: UUID,
        profile: StartupProfile,
    ) -> None:
        try:
            current = self._profiles.get_current(case_id)
        except (AttributeError, KeyError, LookupError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if not isinstance(current, StartupProfile):
            raise StartupGateConflict("research_profile_projection_unavailable")
        if (
            current.case_id != profile.case_id
            or current.profile_id != profile.profile_id
            or current.profile_hash != profile.profile_hash
            or current.data_revision != profile.data_revision
            or current.analysis_stage is not profile.analysis_stage
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")

    def _validate_repository_current_profile_for_preflight(
        self,
        case_id: UUID,
        profile: StartupProfile,
    ) -> None:
        try:
            current = self._profiles.get_current(case_id)
        except (AttributeError, KeyError, LookupError, ValueError) as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        if not isinstance(current, StartupProfile):
            raise StartupGateConflict("research_profile_projection_unavailable")
        if _same_profile_identity(current, profile):
            return
        if not _pending_profile_projection_matches(current, profile):
            raise StartupGateConflict("research_profile_projection_unavailable")

    def _validate_runtime_profile_projection(
        self,
        runtime: dict[str, Any],
        profile: StartupProfile,
        data_revision: int,
    ) -> None:
        _validate_runtime_profile_markers(runtime, profile, data_revision)
        primary_profile_id = runtime.get("primary_profile_id")
        profile_id = str(profile.profile_id)
        if profile.analysis_stage is StartupProfileAnalysisStage.PRIMARY:
            if primary_profile_id is not None and primary_profile_id != profile_id:
                raise StartupGateConflict("research_profile_projection_unavailable")
            return
        if profile.analysis_stage is not StartupProfileAnalysisStage.ENRICHED:
            raise StartupGateConflict("research_profile_projection_unavailable")
        parent = self._profile_by_id(profile.parent_profile_id)
        if (
            parent.case_id != profile.case_id
            or parent.data_revision != profile.data_revision
            or parent.analysis_stage is not StartupProfileAnalysisStage.PRIMARY
        ):
            raise StartupGateConflict("research_profile_projection_unavailable")
        parent_profile_id = str(parent.profile_id)
        if primary_profile_id is not None and primary_profile_id != parent_profile_id:
            raise StartupGateConflict("research_profile_projection_unavailable")

    def _validate_runtime_profile_transition(
        self,
        runtime: dict[str, Any],
        profile: StartupProfile,
        *,
        old_revision: int,
        new_revision: int,
    ) -> None:
        runtime_revision = runtime.get("data_revision")
        if runtime_revision not in {old_revision, new_revision}:
            raise StartupGateConflict("research_profile_projection_unavailable")
        self._validate_runtime_profile_projection(
            {**runtime, "data_revision": old_revision},
            profile,
            old_revision,
        )

    def _thread_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> CopilotThread | None:
        getter = getattr(self._threads, "get_by_idempotency", None)
        if getter is None:
            return None
        return cast(CopilotThread | None, getter(case_id, idempotency_key))

    def _advice_message(
        self,
        case: DueDiligenceCase,
        projection: _StateProjection,
        prompt: str,
        *,
        page_context: str,
        current_section: str,
        focus_key: str | None,
        fallback: str,
    ) -> str:
        if self._copilot_advice_provider is None:
            return fallback
        context = _bounded_advice_context(
            case,
            projection,
            prompt,
            page_context=page_context,
            current_section=current_section,
            focus_key=focus_key,
        )
        try:
            raw = self._copilot_advice_provider.advise(context)
        except (AttributeError, KeyError, OSError, RuntimeError, TimeoutError, TypeError, ValueError):
            return fallback
        message = _provider_message(raw)
        return message or fallback

    def _ensure_case(self, case_id: UUID) -> DueDiligenceCase:
        try:
            return cast(DueDiligenceCase, self._case_repository.get(case_id))
        except KeyError:
            runtime = self._runtime(case_id)
            now = datetime.now(UTC)
            metadata = runtime.get("upload_metadata")
            company_name = (
                metadata.get("company_name")
                if isinstance(metadata, dict) and isinstance(metadata.get("company_name"), str)
                else runtime.get("company_name")
            )
            case = DueDiligenceCase(
                case_id=case_id,
                mode=AnalysisMode.STARTUP,
                entity_name=str(company_name or "Startup case"),
                entity_identifier=str(case_id),
                jurisdiction="unknown",
                scope=("startup_case_copilot",),
                as_of=now,
                base_currency="KZT",
                privacy_policy="startup_local_private",
                budget_policy="offline_deterministic",
                status=CaseStatus.AWAITING_EVIDENCE,
                sensitivity=SensitivityClass.CONFIDENTIAL,
                created_at=now,
                updated_at=now,
                workflow_version="startup-case-copilot-v1",
                data_revision=_revision_from_runtime(runtime),
            )
            try:
                self._case_repository.add(case)
            except ValueError:
                return cast(DueDiligenceCase, self._case_repository.get(case_id))
            return case

    def _runtime(self, case_id: UUID) -> dict[str, Any]:
        runtime = self._workflow_store.load(str(case_id))
        if not runtime.get("case_exists"):
            raise StartupNotFound("case_not_found")
        return cast(dict[str, Any], runtime)

    def _same_case_projection(self, case: DueDiligenceCase) -> _StateProjection:
        try:
            profile = self._profiles.get_current(case.case_id)
        except (KeyError, ValueError):
            profile = None
        if profile is not None:
            facts = _profile_facts(profile)
            if facts:
                return _StateProjection(
                    facts=facts,
                    gaps=_generic_gaps("public_pricing_analogs"),
                    brief_text="",
                )
        brief_text = self._uploaded_brief_text(case.case_id)
        return _projection_from_brief(brief_text, fallback_name=case.entity_name)

    def _uploaded_brief_text(self, case_id: UUID) -> str:
        runtime = self._runtime(case_id)
        documents = runtime.get("documents")
        if not isinstance(documents, list):
            return ""
        for document in documents:
            if not isinstance(document, dict):
                continue
            private_name = document.get("private_name")
            if not isinstance(private_name, str):
                continue
            case_dir = (self._inbox_root / str(case_id)).resolve()
            path = (case_dir / private_name).resolve()
            if not _is_relative_to(path, case_dir):
                continue
            mime_type = str(document.get("declared_mime_type", ""))
            suffix_allowed = path.suffix.casefold() in {".txt", ".md"}
            mime_allowed = mime_type.startswith("text/")
            if not (suffix_allowed or mime_allowed) or not path.exists():
                continue
            return cast(str, path.read_text(encoding="utf-8", errors="replace"))
        case_dir = self._inbox_root / str(case_id)
        if case_dir.is_dir():
            for path in sorted(case_dir.iterdir()):
                if path.is_file() and path.suffix.casefold() in {"", ".bin", ".txt", ".md"}:
                    return cast(str, path.read_text(encoding="utf-8", errors="replace"))
        return ""

    def _next_question(
        self,
        case: DueDiligenceCase,
        projection: _StateProjection,
        *,
        page_context: str = "overview",
        focus_key: str | None = None,
    ) -> str | None:
        content_question = _content_question(projection.brief_text)
        if content_question is not None:
            try:
                self._questions.next_question(
                    case.case_id,
                    page_context=page_context,
                    focus_key=focus_key,
                )
            except (KeyError, ValueError):
                pass
            return content_question
        try:
            question = self._questions.next_question(
                case.case_id,
                page_context=page_context,
                focus_key=focus_key,
            )
        except (KeyError, ValueError):
            return "Which first customer segment and proof point should the founder validate next?"
        return getattr(question, "prompt", None) if question is not None else None

    def _question_selection(
        self,
        case: DueDiligenceCase,
        projection: _StateProjection,
        *,
        page_context: str = "overview",
        focus_key: str | None = None,
    ) -> _QuestionSelection:
        content_question = _content_question(projection.brief_text)
        try:
            descriptor_builder = getattr(self._questions, "next_question_descriptor", None)
            if callable(descriptor_builder):
                descriptor = descriptor_builder(
                    case.case_id,
                    page_context=page_context,
                    focus_key=focus_key,
                )
                if descriptor is not None:
                    typed_descriptor = cast(CaseQuestionDescriptorProjection, descriptor)
                    return _QuestionSelection(typed_descriptor, typed_descriptor.question)
            question = self._questions.next_question(
                case.case_id,
                page_context=page_context,
                focus_key=focus_key,
            )
        except (KeyError, ValueError):
            return _QuestionSelection(None, content_question)
        descriptor_method = getattr(question, "descriptor", None)
        if callable(descriptor_method):
            typed_descriptor = cast(CaseQuestionDescriptorProjection, descriptor_method())
            return _QuestionSelection(typed_descriptor, typed_descriptor.question)
        return _QuestionSelection(
            None,
            content_question or (getattr(question, "prompt", None) if question is not None else None),
        )

    def _append_system_event(
        self,
        case_id: UUID,
        *,
        data_revision: int,
        content: str,
        idempotency_key: str,
    ) -> None:
        try:
            current = self._threads.get_current(case_id)
        except KeyError:
            current = CopilotThread(
                thread_id=_thread_id(case_id),
                case_id=case_id,
                data_revision=data_revision,
            )
        message = CopilotMessage(
            message_id=_message_id(case_id, data_revision, "system", content),
            case_id=case_id,
            data_revision=data_revision,
            role="system_event",
            content=content,
        )
        thread = current.model_copy(
            update={
                "data_revision": data_revision,
                "messages": (*current.messages, message),
            }
        )
        self._threads.save(thread, expected_revision=data_revision, idempotency_key=idempotency_key)

    def _append_copilot_turn(
        self,
        case: DueDiligenceCase,
        *,
        user_content: str,
        assistant_content: str,
        page_context: str,
        current_section: str,
        actions: tuple[ActionAvailabilityProjection, ...],
        idempotency_key: str,
        idempotency_fingerprint: str,
    ) -> CopilotThread:
        try:
            current = self._threads.get_current(case.case_id)
        except KeyError:
            current = CopilotThread(
                thread_id=_thread_id(case.case_id),
                case_id=case.case_id,
                data_revision=case.data_revision,
                messages=(
                    CopilotMessage(
                        message_id=_message_id(case.case_id, case.data_revision, "system", "created"),
                        case_id=case.case_id,
                        data_revision=case.data_revision,
                        role="system_event",
                        content="Case Copilot is ready with same-case facts and scenario boundaries.",
                    ),
                ),
            )
        user = CopilotMessage(
            message_id=_message_id(
                case.case_id,
                case.data_revision,
                f"user:{idempotency_key}",
                user_content,
            ),
            case_id=case.case_id,
            data_revision=case.data_revision,
            role="user",
            content=user_content,
            page_context=page_context,
            current_section=current_section,
            idempotency_fingerprint=idempotency_fingerprint,
        )
        assistant = CopilotMessage(
            message_id=_message_id(
                case.case_id,
                case.data_revision,
                f"assistant:{idempotency_key}",
                assistant_content,
            ),
            case_id=case.case_id,
            data_revision=case.data_revision,
            role="assistant",
            content=assistant_content,
            page_context=page_context,
            current_section=current_section,
            action_refs=tuple(action.action_id for action in actions),
            action_snapshots=tuple(action.model_dump(mode="python") for action in actions),
        )
        thread = current.model_copy(
            update={
                "data_revision": case.data_revision,
                "messages": (*current.messages, user, assistant),
            }
        )
        return cast(
            CopilotThread,
            self._threads.save(
                thread,
                expected_revision=case.data_revision,
                idempotency_key=f"copilot-turn:{idempotency_key}",
            ),
        )

    def _current_scenario_set(self, case: DueDiligenceCase) -> Any:
        try:
            scenario_set = self._scenario_repository.get_current(case.case_id)
        except KeyError:
            return self._scenarios.build(
                case.case_id,
                expected_case_revision=case.data_revision,
                idempotency_key=f"scenario-build:{case.data_revision}",
            )
        if scenario_set.data_revision != case.data_revision:
            return self._scenarios.build(
                case.case_id,
                expected_case_revision=case.data_revision,
                idempotency_key=f"scenario-build:{case.data_revision}",
            )
        return scenario_set

    def _validate_runtime_revision_before_mutation(
        self,
        case_id: UUID,
        expected_revision: int,
    ) -> None:
        runtime_revision = _revision_from_runtime(self._runtime(case_id))
        if runtime_revision != expected_revision:
            raise StartupGateConflict("case_revision_conflict")


class _FactValidationFailure(ValueError):
    def __init__(self, errors: tuple[FieldErrorResponse, ...]) -> None:
        super().__init__("fact_validation_failed")
        self.errors = errors


class _StateProjection:
    def __init__(
        self,
        *,
        facts: list[FactProjection],
        gaps: list[GapProjection],
        brief_text: str,
    ) -> None:
        self.facts = facts
        self.gaps = gaps
        self.brief_text = brief_text


def _fact_validation_errors(request: SaveFounderFactRequest) -> tuple[FieldErrorResponse, ...]:
    errors: list[FieldErrorResponse] = []
    if isinstance(request.value, MoneyFactValue):
        if request.value.amount is None:
            errors.append(FieldErrorResponse(field="amount", message="amount is required"))
        if not _present(request.value.scale):
            errors.append(FieldErrorResponse(field="scale", message="scale is required"))
        if not _present(request.value.currency):
            errors.append(FieldErrorResponse(field="currency", message="currency is required"))
        if request.period is None and _period_required_for_requirement(request.requirement_key):
            errors.append(FieldErrorResponse(field="period", message="period is required"))
    if request.source.kind is CaseValueKind.FOUNDER_STATEMENT and not _present(request.source.declared_source):
        errors.append(FieldErrorResponse(field="declared_source", message="declared_source is required"))
    return tuple(errors)


def _fact_command(case_id: UUID, request: SaveFounderFactRequest) -> SaveFounderStatementCommand:
    return SaveFounderStatementCommand(
        case_id=case_id,
        requirement_key=_canonical_requirement_key(request.requirement_key),
        value=_command_value(request.value),
        currency=getattr(request.value, "currency", None),
        scale=getattr(request.value, "scale", None),
        period=_period_value(request.period),
        declared_source=request.source.declared_source,
        supporting_evidence_refs=(
            (request.source.evidence_ref,) if request.source.evidence_ref is not None else ()
        ),
        rationale=request.note,
        expected_case_revision=request.expected_case_revision,
        idempotency_key=request.idempotency_key,
    )


def _assumption_command(case_id: UUID, request: SaveAssumptionRequest) -> SaveFounderStatementCommand:
    return SaveFounderStatementCommand(
        case_id=case_id,
        requirement_key=_canonical_requirement_key(request.requirement_key),
        value=_command_value(request.value),
        currency=getattr(request.value, "currency", None),
        scale=getattr(request.value, "scale", None),
        period=_period_value(request.period),
        declared_source=request.source.declared_source,
        supporting_evidence_refs=(
            (request.source.evidence_ref,) if request.source.evidence_ref is not None else ()
        ),
        rationale=request.rationale,
        validation_plan=request.validation_plan,
        expected_case_revision=request.expected_case_revision,
        idempotency_key=request.idempotency_key,
    )


def _command_value(value: MoneyFactValue | TextFactValue) -> str:
    if isinstance(value, MoneyFactValue):
        return "" if value.amount is None else str(value.amount)
    return value.value


def _period_value(period: FactPeriod | None) -> str | None:
    if period is None:
        return None
    if period.start and period.end:
        return f"{period.start}/{period.end}"
    return period.value or period.start


def _delta_response(delta: CaseMutationDelta) -> CaseMutationDeltaResponse:
    next_question = delta.next_question
    if next_question is not None and hasattr(next_question, "model_dump"):
        next_question = next_question.model_dump(mode="json")
    return CaseMutationDeltaResponse(
        accepted=delta.accepted,
        old_revision=delta.old_revision,
        new_revision=delta.new_revision,
        changed_keys=delta.changed_keys,
        stale_scenario_ids=delta.stale_scenario_ids,
        stale_report_ids=delta.stale_report_ids,
        metric_before=delta.metric_before,
        metric_after=delta.metric_after,
        readiness_before=delta.readiness_before,
        readiness_after=delta.readiness_after,
        next_question=next_question,
        validation_errors=tuple(
            FieldErrorResponse(field=item.field, message=item.message)
            for item in delta.validation_errors
        ),
        original_draft=delta.original_draft,
    )


def _source_status_rows() -> list[AcceptedInputProjection]:
    return [
        AcceptedInputProjection(field_key=kind.value, kind=kind, status=status, value="")
        for kind, status in _SOURCE_STATUSES.items()
    ]


def _profile_projection_matches_revision(runtime: dict[str, Any], data_revision: int) -> bool:
    profile_id = runtime.get("profile_id")
    primary_profile_id = runtime.get("primary_profile_id")
    return (
        runtime.get("data_revision") == data_revision
        and runtime.get("profile_revision") == data_revision
        and isinstance(profile_id, str)
        and isinstance(runtime.get("profile_hash"), str)
        and (primary_profile_id is None or isinstance(primary_profile_id, str))
    )


def _startup_analysis_revision_payload(
    case_id: UUID,
    *,
    runtime: dict[str, Any],
    data_revision: int,
) -> dict[str, Any] | None:
    raw_document_ids = runtime.get("source_document_ids")
    raw_source_refs = runtime.get("source_refs")
    fixture_mode = runtime.get("fixture_mode")
    execution_mode = runtime.get("provider_status")
    if (
        not isinstance(raw_document_ids, list)
        or not raw_document_ids
        or not all(isinstance(item, str) and item for item in raw_document_ids)
        or not isinstance(raw_source_refs, list)
        or not raw_source_refs
        or runtime.get("source_refs_revision") != data_revision
        or fixture_mode not in {"live", "deterministic_offline"}
        or execution_mode not in {
            "configured",
            "unavailable",
            "deterministic_offline_fixture",
        }
    ):
        return None
    source_refs: list[dict[str, str]] = []
    for item in raw_source_refs:
        if not isinstance(item, dict):
            return None
        document_id = item.get("document_id")
        private_name = item.get("private_name")
        content_sha256 = item.get("content_sha256")
        if (
            not isinstance(document_id, str)
            or not document_id
            or not isinstance(private_name, str)
            or not private_name
            or not isinstance(content_sha256, str)
            or not content_sha256
        ):
            return None
        source_refs.append(
            {
                "document_id": document_id,
                "private_name": private_name,
                "content_sha256": content_sha256,
            }
        )
    case_id_text = str(case_id)
    return {
        "case_id": case_id_text,
        "run_id": f"startup-api-{case_id_text}",
        "correlation_id": case_id_text,
        "source_document_ids": list(raw_document_ids),
        "source_refs": source_refs,
        "data_revision": data_revision,
        "fixture_mode": fixture_mode,
        "execution_mode": execution_mode,
    }


def _runtime_has_profile_projection(runtime: dict[str, Any]) -> bool:
    return any(
        runtime.get(key) is not None
        for key in (
            "profile_id",
            "profile_hash",
            "profile_revision",
            "primary_profile_id",
        )
    )


def _validate_runtime_profile_markers(
    runtime: dict[str, Any],
    profile: StartupProfile,
    data_revision: int,
) -> None:
    profile_id = runtime.get("profile_id")
    profile_hash = runtime.get("profile_hash")
    profile_revision = runtime.get("profile_revision")
    if (
        runtime.get("data_revision") != data_revision
        or not isinstance(profile_id, str)
        or not isinstance(profile_hash, str)
        or type(profile_revision) is not int
        or profile_id != str(profile.profile_id)
        or profile_hash != profile.profile_hash
        or profile_revision != profile.data_revision
    ):
        raise StartupGateConflict("research_profile_projection_unavailable")


def _same_profile_identity(current: StartupProfile, profile: StartupProfile) -> bool:
    return (
        current.case_id == profile.case_id
        and current.profile_id == profile.profile_id
        and current.profile_hash == profile.profile_hash
        and current.data_revision == profile.data_revision
        and current.analysis_stage is profile.analysis_stage
    )


def _pending_profile_projection_matches(current: StartupProfile, profile: StartupProfile) -> bool:
    return (
        current.case_id == profile.case_id
        and current.data_revision == profile.data_revision + 1
        and current.analysis_stage is profile.analysis_stage
        and current.schema_version == profile.schema_version
        and current.profile_version == profile.profile_version
        and current.extractor_version == profile.extractor_version
        and current.source_hashes == profile.source_hashes
        and current.parse_outcomes == profile.parse_outcomes
        and current.fields == profile.fields
        and current.gap_codes == profile.gap_codes
        and current.contradiction_ids == profile.contradiction_ids
    )


def _profile_projection_update(
    profile: StartupProfile,
    *,
    primary_profile: StartupProfile | None = None,
) -> dict[str, Any]:
    primary = primary_profile or profile
    if primary.analysis_stage is not StartupProfileAnalysisStage.PRIMARY:
        raise StartupGateConflict("research_profile_projection_unavailable")
    if profile.analysis_stage is StartupProfileAnalysisStage.ENRICHED and profile.parent_profile_id != primary.profile_id:
        raise StartupGateConflict("research_profile_projection_unavailable")
    return {
        "profile_id": str(profile.profile_id),
        "profile_hash": profile.profile_hash,
        "profile_revision": profile.data_revision,
        "primary_profile_id": str(primary.profile_id),
    }


def _product_validation_projection_update(
    runtime: dict[str, Any],
    snapshot: StartupProductValidationSnapshot,
) -> dict[str, Any]:
    artifact = {
        "schema_version": snapshot.schema_version,
        "snapshot": snapshot.model_dump(mode="json"),
    }
    history = _runtime_history(
        runtime,
        "startup_product_validation_history",
        identity_key="snapshot_id",
        identity_value=str(snapshot.snapshot_id),
    )
    history.append(
        {
            "snapshot_id": str(snapshot.snapshot_id),
            "snapshot_hash": snapshot.snapshot_hash,
            "profile_revision": snapshot.profile_revision,
        }
    )
    return {
        "startup_product_validation_artifact": artifact,
        "startup_product_validation_history": history[-4:],
        "product_validation_snapshot_id": str(snapshot.snapshot_id),
        "product_validation_snapshot_hash": snapshot.snapshot_hash,
        "product_validation_snapshot_revision": snapshot.profile_revision,
    }


def _market_research_projection_update(snapshot: StartupMarketResearchSnapshot) -> dict[str, Any]:
    return {
        "startup_market_research_artifact": {
            "schema_version": snapshot.schema_version,
            "snapshot": snapshot.model_dump(mode="json"),
        },
        "market_research_snapshot_id": str(snapshot.snapshot_id),
        "market_research_snapshot_hash": snapshot.snapshot_hash,
        "market_research_snapshot_revision": snapshot.data_revision,
    }


def _public_research_source_id(source_refs: list[str] | tuple[str, ...], url: str) -> UUID:
    for value in source_refs:
        try:
            return UUID(value)
        except (TypeError, ValueError):
            continue
    return uuid5(NAMESPACE_URL, f"public-research-source:{url}")


def _date_from_iso(value: str) -> date:
    return date.fromisoformat(value)


def _datetime_from_iso_date(value: str) -> datetime:
    as_date = _date_from_iso(value)
    return datetime(as_date.year, as_date.month, as_date.day, tzinfo=UTC)


def _public_research_source_hash(url: str, publisher: str, retrieval_date: str) -> str:
    payload = f"{url}|{publisher}|{retrieval_date}".encode()
    return f"sha256:{sha256(payload).hexdigest()}"


def _public_research_confidence(value: str) -> Decimal:
    return {
        "low": Decimal("0.3"),
        "medium": Decimal("0.6"),
        "high": Decimal("0.8"),
    }.get(value, Decimal("0.5"))


def _readiness_projection_update(snapshot: StartupReadinessSnapshot) -> dict[str, Any]:
    return {
        "startup_readiness_artifact": {
            "schema_version": snapshot.schema_version,
            "snapshot": snapshot.model_dump(mode="json"),
        },
        "readiness_snapshot_id": str(snapshot.snapshot_id),
        "readiness_snapshot_hash": snapshot.snapshot_hash,
        "readiness_snapshot_revision": snapshot.profile_revision,
    }


def _gtm_projection_update(runtime: dict[str, Any], snapshot: Any) -> dict[str, Any]:
    artifact = {
        "schema_version": snapshot.schema_version,
        "snapshot": snapshot.model_dump(mode="json"),
    }
    history = _runtime_history(
        runtime,
        "startup_gtm_history",
        identity_key="snapshot_id",
        identity_value=str(snapshot.snapshot_id),
    )
    history.append(
        {
            "snapshot_id": str(snapshot.snapshot_id),
            "snapshot_hash": snapshot.snapshot_hash,
            "data_revision": snapshot.data_revision,
        }
    )
    return {
        "startup_gtm_artifact": artifact,
        "startup_gtm_history": history[-4:],
        "gtm_snapshot_id": str(snapshot.snapshot_id),
        "gtm_snapshot_hash": snapshot.snapshot_hash,
        "gtm_snapshot_revision": snapshot.data_revision,
    }


def _runtime_history(
    runtime: dict[str, Any],
    key: str,
    *,
    identity_key: str,
    identity_value: str,
) -> list[dict[str, Any]]:
    raw_history = runtime.get(key, [])
    if not isinstance(raw_history, list):
        return []
    return [
        dict(item)
        for item in raw_history
        if isinstance(item, dict) and item.get(identity_key) != identity_value
    ]


def _runtime_has_gtm_projection(runtime: dict[str, Any]) -> bool:
    return (
        isinstance(runtime.get("startup_gtm_artifact"), dict)
        or isinstance(runtime.get("gtm_snapshot_id"), str)
        or isinstance(runtime.get("gtm_snapshot_hash"), str)
        or type(runtime.get("gtm_snapshot_revision")) is int
    )


def _runtime_has_launch_pack_projection(runtime: dict[str, Any]) -> bool:
    return any(
        isinstance(runtime.get(key), dict)
        for key in (
            "startup_product_validation_artifact",
            "startup_market_research_artifact",
            "startup_readiness_artifact",
            "startup_gtm_artifact",
        )
    ) or any(runtime.get(key) is not None for key in _LAUNCH_PACK_MARKER_KEYS)


def _launch_pack_marker_update(update: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in update.items() if key in _LAUNCH_PACK_MARKER_KEYS}


def _launch_pack_marker_reset() -> dict[str, Any]:
    return {key: None for key in _LAUNCH_PACK_MARKER_KEYS}


def _profile_marker_update(runtime: dict[str, Any]) -> dict[str, Any]:
    marker_keys = {
        "profile_id",
        "profile_hash",
        "profile_revision",
        "primary_profile_id",
    }
    return {key: value for key, value in runtime.items() if key in marker_keys}


def _runtime_string_refs(value: Any) -> list[str]:
    if value is None:
        return []
    items = [value] if isinstance(value, str | UUID) else list(value)
    return [str(item) for item in items if isinstance(item, str | UUID)]


def _runtime_string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str | UUID) and isinstance(item, str)
    }


def _accepted_input_from_statement(statement: FounderStatement) -> AcceptedInputProjection:
    return AcceptedInputProjection(
        field_key=statement.field_key,
        kind=statement.provenance,
        status="accepted",
        value=statement.value,
        period=statement.period,
        rationale=statement.rationale,
        validation_plan=statement.validation_plan,
        declared_source=statement.declared_source,
        source_refs=tuple(dict.fromkeys((statement.statement_id, *statement.source_refs))),
    )


def _accepted_input_from_public_benchmark(input_value: ScenarioInput) -> AcceptedInputProjection:
    return AcceptedInputProjection(
        field_key=input_value.input_key,
        kind=CaseValueKind.PUBLIC_BENCHMARK,
        status="accepted",
        value=_scenario_input_display_value(input_value),
        period=input_value.period,
        rationale=input_value.rationale,
        validation_plan=input_value.validation_plan,
        source_refs=tuple(dict.fromkeys((input_value.input_id, *input_value.source_refs))),
    )


def _scenario_input_display_value(input_value: ScenarioInput) -> str:
    value_range = input_value.value_range
    unit_suffix = f" {input_value.unit}" if input_value.unit else ""
    if value_range.lower == value_range.upper:
        return f"{_decimal_display(value_range.lower)}{unit_suffix}"
    return (
        f"{_decimal_display(value_range.lower)}-"
        f"{_decimal_display(value_range.upper)}{unit_suffix}"
    )


def _decimal_display(value: Any) -> str:
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def _turn_fingerprint(request: PostCopilotMessageRequest, sanitized_user_message: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            (
                "copilot-turn-fingerprint:"
                f"{sanitized_user_message}:"
                f"{request.page_context}:"
                f"{request.current_section}:"
                f"{request.focus_key or ''}"
            ),
        )
    )


def _last_turn_fingerprint(thread: CopilotThread) -> str | None:
    for message in reversed(thread.messages):
        if message.role == "user" and message.idempotency_fingerprint is not None:
            return message.idempotency_fingerprint
    return None


def _validated_actions_from_message(message: CopilotMessage) -> list[ActionAvailabilityProjection]:
    actions: list[ActionAvailabilityProjection] = []
    for item in message.action_snapshots:
        try:
            actions.append(ActionAvailabilityProjection.model_validate(item))
        except (TypeError, ValueError):
            raise StartupGateConflict("copilot_action_snapshot_corrupt") from None
    if len(actions) != len(_CANONICAL_ACTION_KEYS):
        raise StartupGateConflict("copilot_action_snapshot_corrupt")
    action_keys = tuple(action.action for action in actions)
    if action_keys != _CANONICAL_ACTION_KEYS:
        raise StartupGateConflict("copilot_action_snapshot_corrupt")
    action_ids = tuple(action.action_id for action in actions)
    if len(set(action_ids)) != len(action_ids):
        raise StartupGateConflict("copilot_action_snapshot_corrupt")
    if action_ids != message.action_refs:
        raise StartupGateConflict("copilot_action_snapshot_corrupt")
    for action in actions:
        if action.action_id != _action_id(message.case_id, message.data_revision, action.action):
            raise StartupGateConflict("copilot_action_snapshot_corrupt")
        if action.action == "open_document_upload" and action.payload.get("case_id") != str(
            message.case_id
        ):
            raise StartupGateConflict("copilot_action_snapshot_corrupt")
        if (
            action.action == "prepare_public_research"
            and action.payload.get("expected_case_revision") != message.data_revision
        ):
            raise StartupGateConflict("copilot_action_snapshot_corrupt")
    return actions


def _statement_by_idempotency(
    repository: Any,
    case_id: UUID,
    idempotency_key: str,
) -> FounderStatement | None:
    getter = getattr(repository, "get_by_idempotency", None)
    if getter is None:
        return None
    statement = getter(case_id, idempotency_key)
    return cast(FounderStatement | None, statement)


def _has_fact_idempotency(repository: Any, case_id: UUID, idempotency_key: str) -> bool:
    getter = getattr(repository, "get_by_idempotency", None)
    if getter is None:
        return False
    return getter(case_id, idempotency_key) is not None


def _profile_facts(profile: Any) -> list[FactProjection]:
    facts: list[FactProjection] = []
    fields = getattr(profile, "fields", {})
    if not isinstance(fields, dict):
        return facts
    for key, field in fields.items():
        values = tuple(getattr(field, "values", ()) or ())
        if not values:
            continue
        status = str(getattr(field, "status", ""))
        source_type = (
            CaseValueKind.SOURCE_FACT
            if status == "source_fact"
            else CaseValueKind.FOUNDER_STATEMENT
        )
        facts.append(FactProjection(field_key=str(key), value=str(values[0]), source_type=source_type))
    return facts


def _case_stage(question_service: Any, profile_repository: Any, case_id: UUID) -> CaseStage:
    resolver = getattr(question_service, "stage", None)
    if resolver is not None:
        try:
            stage = resolver(case_id)
        except (KeyError, ValueError):
            stage = None
        if isinstance(stage, CaseStage):
            return stage
        if isinstance(stage, str):
            try:
                return CaseStage(stage)
            except ValueError:
                pass
    return resolve_case_stage(profile_repository, case_id)


def _projection_from_brief(brief: str, *, fallback_name: str) -> _StateProjection:
    name = _extract_after(brief, r"Founder idea brief:\s*([^\n]+)") or fallback_name
    concept = _section(brief, "Concept")
    buyer = _section(brief, "Buyer")
    user = _section(brief, "User")
    geography = _section(brief, "Geography")
    pricing = _section(brief, "Pricing hypothesis")
    launch_window = _section(brief, "Launch window")
    launch_constraints = _section(brief, "Launch constraints")
    segment = _customer_segment(concept)
    geography_value = _geography_value(geography)
    has_constraints = bool(launch_constraints)
    facts = [FactProjection(field_key="startup_name", value=name, source_type=CaseValueKind.SOURCE_FACT)]
    facts.extend(
        _content_facts(
            brief=brief,
            concept=concept,
            buyer=buyer,
            user=user,
            geography=geography_value,
            pricing=pricing,
            launch_window=launch_window,
            launch_constraints=launch_constraints,
            customer_segment=segment,
        )
    )
    public_gap = "regulatory_context" if has_constraints else "public_pricing_analogs"
    return _StateProjection(
        facts=facts,
        gaps=_generic_gaps(public_gap),
        brief_text=brief,
    )


def _content_facts(
    *,
    brief: str,
    concept: str,
    buyer: str,
    user: str,
    geography: str,
    pricing: str,
    launch_window: str,
    launch_constraints: str,
    customer_segment: str,
) -> list[FactProjection]:
    if not any((concept, buyer, user, geography, pricing, launch_window, launch_constraints)):
        return [
            FactProjection(field_key="one_line_description", value=_first_sentence(brief), source_type=CaseValueKind.SOURCE_FACT),
            FactProjection(field_key="buyer", value=_extract_after(brief, r"Buyers are ([^.;]+)") or "Unknown", source_type=CaseValueKind.SOURCE_FACT),
            FactProjection(field_key="user", value=_extract_after(brief, r"users are ([^.;]+)") or "Unknown", source_type=CaseValueKind.SOURCE_FACT),
            FactProjection(field_key="customer_segment", value=_extract_after(brief, r"first launch wedge is ([^.;]+)") or "Unknown segment", source_type=CaseValueKind.SOURCE_FACT),
        ]
    facts = [
        FactProjection(field_key="customer_segment", value=customer_segment, source_type=CaseValueKind.SOURCE_FACT),
        FactProjection(field_key="buyer", value=_leading_phrase(buyer, " who ", " at "), source_type=CaseValueKind.SOURCE_FACT),
        FactProjection(field_key="user", value=_leading_phrase(user, " who ", " at "), source_type=CaseValueKind.SOURCE_FACT),
    ]
    if geography:
        facts.append(FactProjection(field_key="geography", value=geography, source_type=CaseValueKind.SOURCE_FACT))
    launch_constraint = _launch_constraint_value(launch_constraints)
    if launch_constraint:
        facts.append(
            FactProjection(
                field_key="launch_constraint",
                value=launch_constraint,
                source_type=CaseValueKind.SOURCE_FACT,
            )
        )
    launch_value = _launch_window_value(launch_window)
    if launch_value:
        facts.append(
            FactProjection(
                field_key="launch_window",
                value=launch_value,
                source_type=CaseValueKind.SOURCE_FACT,
            )
        )
    pricing_value = _pricing_value(pricing)
    if pricing_value:
        facts.append(
            FactProjection(
                field_key="pricing_revenue_model",
                value=pricing_value,
                source_type=CaseValueKind.FOUNDER_STATEMENT,
            )
        )
    if len(facts) > 2:
        return facts
    return [
        FactProjection(field_key="one_line_description", value=_first_sentence(concept or brief), source_type=CaseValueKind.SOURCE_FACT),
        FactProjection(field_key="buyer", value=_extract_after(concept, r"Buyers are ([^.;]+)") or _first_sentence(buyer), source_type=CaseValueKind.SOURCE_FACT),
        FactProjection(field_key="user", value=_extract_after(concept, r"users are ([^.;]+)") or _first_sentence(user), source_type=CaseValueKind.SOURCE_FACT),
        FactProjection(field_key="customer_segment", value=_extract_after(concept, r"first launch wedge is ([^.;]+)") or customer_segment, source_type=CaseValueKind.SOURCE_FACT),
    ]


def _generic_gaps(public_gap: str) -> list[GapProjection]:
    private_keys = ["monthly_recurring_revenue", "cash_balance", "customer_count"]
    if public_gap == "public_pricing_analogs":
        private_keys = ["monthly_recurring_revenue", "monthly_net_burn", "customer_count"]
    return [
        *[
            GapProjection(
                gap_code=f"input.missing:{key}",
                field_key=key,
                privacy_class="private_startup_metric",
                allowed_action="manual_fact_intake",
            )
            for key in private_keys
        ],
        GapProjection(
            gap_code=f"input.missing:{public_gap}",
            field_key=public_gap,
            privacy_class="public_market_context",
            allowed_action="prepare_public_research",
        ),
    ]


def _scenario_metrics_from_set(scenario_set: Any) -> list[ScenarioMetricProjection]:
    scenario_keys = ("conservative", "base", "optimistic")
    variants = getattr(scenario_set, "scenarios", {})
    selected_key = getattr(scenario_set, "selected_scenario_key", "base")
    selected = variants.get(selected_key)
    if selected is None:
        return []
    metrics: list[ScenarioMetricProjection] = []
    for metric_key, metric in selected.metrics.items():
        ranges: dict[str, str | None] = {}
        for scenario_key in scenario_keys:
            variant = variants.get(scenario_key)
            variant_metric = None if variant is None else variant.metrics.get(metric_key)
            value_range = None if variant_metric is None else variant_metric.value_range
            if value_range is None:
                ranges[scenario_key] = None
            else:
                ranges[scenario_key] = f"{value_range.lower}:{value_range.upper}"
        metrics.append(
            ScenarioMetricProjection(
                metric_key=metric.metric_key,
                label=_metric_label(metric.metric_key),
                source_type=metric.provenance,
                value=None,
                range=ranges,
                formula=metric.formula_key,
                dependencies=[str(item) for item in metric.dependency_refs],
                unit=metric.unit,
                period=metric.period or "",
                confidence=metric.confidence,
                source_refs=[str(item) for item in metric.source_refs],
                what_would_confirm=metric.what_would_confirm,
                validation_plan=metric.validation_plan,
            )
        )
    return metrics


def _typed_actions(
    case: DueDiligenceCase,
    projection: _StateProjection,
    *,
    question_descriptor: CaseQuestionDescriptorProjection | None = None,
    acquisition_modes: ResearchAcquisitionModeCapability | None = None,
) -> list[ActionAvailabilityProjection]:
    founder_input_key = question_descriptor.field_key if question_descriptor is not None else next(
        (gap.field_key for gap in projection.gaps if gap.privacy_class == "private_startup_metric"),
        "monthly_recurring_revenue",
    )
    public_gap = next(
        (gap.field_key for gap in projection.gaps if gap.allowed_action == "prepare_public_research"),
        "public_pricing_analogs",
    )
    mode_capability: ResearchAcquisitionModeCapability = acquisition_modes or {
        "available": (),
        "unavailable": ("live_public_research", "deterministic_offline_fixture"),
        "default": "live_public_research",
    }
    available_modes = mode_capability["available"]
    unavailable_modes = mode_capability["unavailable"]
    default_mode = mode_capability["default"]
    fact_count = len(projection.facts)
    return [
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "open_fact_input"),
            action="open_fact_input",
            status="requires_input",
            handler="openFactInput",
            reason="Private operating metrics require explicit founder entry.",
            effect_preview=f"Open manual founder input for {founder_input_key}; no public research fills it.",
            payload={"field_key": founder_input_key, "provenance": CaseValueKind.FOUNDER_STATEMENT.value},
        ),
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "open_document_upload"),
            action="open_document_upload",
            status="available",
            handler="openDocumentUpload",
            reason=None,
            effect_preview="Open same-case document upload for founder-controlled evidence.",
            payload={"case_id": str(case.case_id)},
        ),
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "prepare_public_research"),
            action="prepare_public_research",
            status="requires_consent",
            handler="prepareResearchPlan",
            reason="Public research requires explicit consent before any provider call.",
            effect_preview=(
                f"Prepare a consent-gated public benchmark plan for {public_gap}; "
                "private actuals stay manual-only."
            ),
            payload={
                "focus": public_gap,
                "expected_case_revision": case.data_revision,
                "available_acquisition_modes": available_modes,
                "unavailable_acquisition_modes": unavailable_modes,
                "default_acquisition_mode": default_mode,
            },
        ),
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "explain_metric"),
            action="explain_metric",
            status="available",
            handler="openMetricExplanation",
            reason=None,
            effect_preview="Explain scenario metric provenance, range, formula, dependencies, and validation plan.",
            payload={"metric_key": "mrr"},
        ),
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "navigate"),
            action="navigate",
            status="available",
            handler="navigate",
            reason=None,
            effect_preview="Navigate to scenario cards without mutating evidence or assumptions.",
            payload={"target": "scenarios"},
        ),
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "prepare_asset"),
            action="prepare_asset",
            status="blocked",
            handler=None,
            reason="Launch-pack asset generation is not available until scenario review is complete.",
            effect_preview="Would prepare a founder-facing launch asset after accepted scenario review.",
            payload={"required_step": "review_scenarios"},
        ),
        ActionAvailabilityProjection(
            action_id=_action_id(case.case_id, case.data_revision, "review_improvements"),
            action="review_improvements",
            status="blocked" if fact_count < 2 else "available",
            handler=None if fact_count < 2 else "openImprovementReview",
            reason=None if fact_count >= 2 else "At least two same-case facts are required first.",
            effect_preview="Review current gaps and non-mutating improvement suggestions for this case.",
            payload={"same_case_fact_count": fact_count},
        ),
    ]


def _assistant_message(
    case: DueDiligenceCase,
    projection: _StateProjection,
    prompt: str,
) -> str:
    fact_keys = ", ".join(fact.field_key for fact in projection.facts[:3]) or "no confirmed fields"
    gap_keys = ", ".join(gap.field_key for gap in projection.gaps[:3]) or "no prioritized gaps"
    return (
        f"For {case.entity_name}, I can work from same-case fields ({fact_keys}). "
        f"Next question: {prompt} Current priority gaps: {gap_keys}."
    )


def _bounded_advice_context(
    case: DueDiligenceCase,
    projection: _StateProjection,
    prompt: str,
    *,
    page_context: str,
    current_section: str,
    focus_key: str | None,
) -> dict[str, Any]:
    return {
        "case_id": str(case.case_id),
        "data_revision": case.data_revision,
        "company_name": case.entity_name,
        "page_context": page_context,
        "current_section": current_section,
        "focus_key": focus_key,
        "next_question": prompt,
        "facts": [
            {
                "field_key": fact.field_key,
                "source_type": fact.source_type.value,
            }
            for fact in projection.facts[:8]
        ],
        "gaps": [
            {
                "field_key": gap.field_key,
                "privacy_class": gap.privacy_class,
                "allowed_action": gap.allowed_action,
            }
            for gap in projection.gaps[:8]
        ],
    }


def _provider_message(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    message = raw.get("message")
    if not isinstance(message, str):
        return None
    normalized = " ".join(message.strip().split())
    return normalized[:1200] if normalized else None


_LOCAL_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\[^\s]+|/(?:Users|home|var|tmp|mnt)/[^\s]+|\\\\[^\s]+)",
    flags=re.IGNORECASE,
)
_DOCUMENT_NAME_PATTERN = re.compile(r"\b[^\s\\/]+\.(?:pdf|docx?|xlsx?|pptx?|txt|md)\b", flags=re.IGNORECASE)
_SECRET_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_]*TOKEN[A-Za-z0-9_]*)\b")


def _sanitize_copilot_text(value: str) -> str:
    text = " ".join(value.strip().split())
    text = _LOCAL_PATH_PATTERN.sub("[redacted-local-path]", text)
    text = _DOCUMENT_NAME_PATTERN.sub("[redacted-document-name]", text)
    text = _SECRET_PATTERN.sub("[redacted-secret]", text)
    return text[:1200] or "User asked for next-step guidance."


def _metric_label(metric_key: str) -> str:
    return metric_key.replace("_", " ").title()


def _content_question(brief: str) -> str | None:
    concept = _section(brief, "Concept")
    segment = _customer_segment(concept)
    launch_constraints = _section(brief, "Launch constraints")
    if launch_constraints:
        role = _constraint_role(launch_constraints, segment)
        focus = "follow-up quality" if "follow-up" in concept.casefold() else "workflow quality"
        return (
            f"Which {role} role owns {focus}, and what non-financial proof shows "
            f"the service can fit {role} operations safely?"
        )
    launch_window = _section(brief, "Launch window")
    if launch_window:
        scope = _workflow_scope(segment)
        return (
            f"Which {scope} workflow is the first launch wedge, and what evidence "
            "proves the pain is urgent enough to pay for?"
        )
    if brief.strip():
        return "Which first customer segment has the urgent workflow pain, and what non-financial proof should validate it next?"
    return None


def _thread_id(case_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"copilot-thread:{case_id}")


def _message_id(case_id: UUID, revision: int, role: str, content: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"copilot-message:{case_id}:{revision}:{role}:{content}")


def _action_id(case_id: UUID, revision: int, action_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"copilot-action:{case_id}:{revision}:{action_key}")


def _revision_from_runtime(runtime: dict[str, Any]) -> int:
    revision = runtime.get("data_revision", runtime.get("source_refs_revision"))
    return revision if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 1 else 1


def _normalize_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _canonical_requirement_key(value: str) -> str:
    normalized = _normalize_key(value)
    return _REQUIREMENT_KEY_ALIASES.get(normalized, normalized)


def _period_required_for_requirement(value: str) -> bool:
    requirement = requirement_registry().get(_canonical_requirement_key(value))
    if requirement is None:
        return True
    return requirement.input_schema.get("period") == "required"


def _present(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _is_relative_to(path: Any, parent: Any) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _section(text: str, heading: str) -> str:
    pattern = rf"{re.escape(heading)}:\s*(.*?)(?:\n[A-Z][A-Za-z ]+:\n|\Z)"
    match = re.search(pattern, text, flags=re.DOTALL)
    return " ".join(match.group(1).strip().split()) if match else ""


def _extract_after(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    return " ".join(match.group(1).strip().split())


def _first_sentence(text: str) -> str:
    stripped = " ".join(text.strip().split())
    if not stripped:
        return "Unknown"
    return re.split(r"(?<=[.!?])\s+", stripped)[0].rstrip(".")


def _leading_phrase(text: str, *markers: str) -> str:
    if not text:
        return "Unknown"
    for marker in markers:
        if marker in text:
            return text.split(marker, 1)[0].strip(" .")
    return _first_sentence(text)


def _customer_segment(concept: str) -> str:
    match = re.search(r"\bfor\s+(.+?)(?:\s+(?:that|who|which|because|where)\b|[.;]|\Z)", concept, flags=re.IGNORECASE)
    if match is None:
        return "Unknown segment"
    return _sentence_case(" ".join(match.group(1).strip().split()))


def _geography_value(geography: str) -> str:
    match = re.search(r"planned for\s+(.+?)(?:,\s*(?:with|where)\b|[.;]|\Z)", geography, flags=re.IGNORECASE)
    value = match.group(1) if match is not None else geography
    value = re.sub(
        r"^(?:[a-z-]+\s+)?(?:clinics|groups|teams|companies|practices|studios)\s+in\s+",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return " ".join(value.strip(" .").split())


def _pricing_value(pricing: str) -> str | None:
    if not pricing:
        return None
    paid = re.search(r"\bpaid\s+(.+?)(?:\.|\Z)", pricing, flags=re.IGNORECASE)
    if paid is not None:
        phrase = paid.group(1)
        phrase = re.sub(r",\s+plus\s+an?\s+", " plus ", phrase, flags=re.IGNORECASE)
        phrase = re.sub(r"\s+for\s+.+$", "", phrase, flags=re.IGNORECASE)
        return f"{_sentence_case(phrase)} hypothesis"
    prefer = re.search(r"\bprefer\s+(.+?)(?:\.|\Z)", pricing, flags=re.IGNORECASE)
    if prefer is not None:
        phrase = prefer.group(1)
        phrase = re.sub(r"\s+with\s+ongoing\s+support\b", "", phrase, flags=re.IGNORECASE)
        phrase = re.sub(r"^(?:an?|the)\s+", "", phrase, flags=re.IGNORECASE)
        phrase = re.sub(r"(?<=,\s)(?:an?|the)\s+", "", phrase, flags=re.IGNORECASE)
        phrase = re.sub(r"(?<=\bor\s)(?:an?|the)\s+", "", phrase, flags=re.IGNORECASE)
        return f"{_sentence_case(phrase)} hypothesis"
    return f"{_sentence_case(_first_sentence(pricing))} hypothesis"


def _launch_window_value(launch_window: str) -> str | None:
    if not launch_window:
        return None
    match = re.search(r"\b(Q[1-4]\s+\d{4})\b", launch_window, flags=re.IGNORECASE)
    if match is None:
        return _first_sentence(launch_window)
    return f"{match.group(1).upper()} pilot window"


def _launch_constraint_value(launch_constraints: str) -> str | None:
    if not launch_constraints:
        return None
    match = re.search(r"\buntil\s+(.+?)\s+are\s+reviewed\b", launch_constraints, flags=re.IGNORECASE)
    if match is None:
        return _first_sentence(launch_constraints)
    return f"{_sentence_case(match.group(1))} must be reviewed"


def _scenario_unit(geography: str) -> str:
    return "KZT/month" if "Kazakhstan" in geography else "USD/month"


def _dependency_noun(segment: str) -> str:
    for word in reversed(re.findall(r"[A-Za-z]+", segment.casefold())):
        singular = _singular(word)
        if singular not in {"and", "or", "the", "for", "active", "count", "pricing", "average", "contract", "value"}:
            return singular
    return "account"


def _active_count_noun(dependencies: tuple[str, ...]) -> str:
    for dependency in dependencies:
        match = re.fullmatch(r"active_(.+)_count", dependency)
        if match is not None:
            return match.group(1)
    return "account"


def _constraint_role(launch_constraints: str, segment: str) -> str:
    match = re.search(r"\b([a-z-]+)\s+staff\s+workflow\b", launch_constraints, flags=re.IGNORECASE)
    if match is not None:
        return match.group(1).casefold()
    return _dependency_noun(segment)


def _workflow_scope(segment: str) -> str:
    nouns = [
        _singular(word)
        for word in re.findall(r"[A-Za-z]+", segment.casefold())
        if word.casefold() not in {"central", "asian", "regional", "independent", "and"}
    ]
    if len(nouns) >= 2:
        return f"{nouns[0]} or {nouns[-1]}"
    return nouns[0] if nouns else "customer"


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return f"{word[:-3]}y"
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _sentence_case(value: str) -> str:
    normalized = " ".join(value.strip(" .").split())
    return f"{normalized[:1].upper()}{normalized[1:]}" if normalized else normalized


__all__ = ["CaseCopilotService", "_FactValidationFailure"]
