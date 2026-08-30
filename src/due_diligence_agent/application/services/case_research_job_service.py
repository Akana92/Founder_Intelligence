from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from due_diligence_agent.application.case_copilot_contracts import (
    PrepareResearchPlanRequest,
    QueueResearchJobRequest,
    RequestedResearchAcquisitionMode,
    ResearchBenchmarkEntryProjection,
    ResearchJobResponse,
    ResearchPlanResponse,
    ResearchRejectedEntryProjection,
)
from due_diligence_agent.application.policies.budget import BudgetExceeded
from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
)
from due_diligence_agent.application.startup_cases import (
    StartupGateConflict,
    StartupNotFound,
    StartupValidationError,
)
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.market import (
    MarketSizingAssumption,
    MarketSizingEstimate,
    StartupCompetitor,
    StartupMarketResearchSnapshot,
    StartupMarketSizing,
    StartupResearchPlan,
    StartupResearchSource,
    StartupResearchSourceMode,
    StartupResearchSourceStatus,
)
from due_diligence_agent.domain.startup.profile import StartupProfileAnalysisStage
from due_diligence_agent.domain.startup.scenario import ScenarioInput, ScenarioRange
from due_diligence_agent.ports.repositories import (
    CaseResearchJob,
    CaseResearchPlan,
    PublicBenchmarkEntry,
    RejectedResearchEntry,
    ResearchAcquisitionMode,
)

_ALLOWED_PUBLIC_FOCUS = {
    "market",
    "icp",
    "competitors",
    "alternatives",
    "channels",
    "public_pricing_analogs",
    "unit_economics_benchmarks",
    "regulatory_context",
}
_PRIVATE_RESEARCH_KEYS = {
    "mrr",
    "arr",
    "monthly_recurring_revenue",
    "annual_recurring_revenue",
    "recognized_revenue",
    "revenue",
    "burn",
    "monthly_net_burn",
    "cash",
    "cash_balance",
    "runway",
    "customer_count",
    "actual_customers",
    "private_churn",
    "private_retention",
    "private_cac",
    "private_margin",
    "churn",
    "retention",
    "cac",
    "margin",
    "contracts",
    "contract_register",
    "invoices",
    "invoice_register",
    "bank",
    "bank_data",
}
_MANUAL_ONLY_KEYS = (
    "monthly_recurring_revenue",
    "annual_recurring_revenue",
    "recognized_revenue",
    "monthly_net_burn",
    "cash",
    "cash_balance",
    "runway",
    "actual_customers",
    "private_churn",
    "private_retention",
    "private_cac",
    "private_margin",
    "contracts",
    "contract_register",
    "invoices",
    "invoice_register",
    "bank",
    "bank_data",
)
_PRIVATE_TEXT_RE = re.compile(
    r"(?i)\b(?:mrr|arr|monthly[_ -]?recurring[_ -]?revenue|annual[_ -]?recurring[_ -]?revenue|"
    r"recognized[_ -]?revenue|revenue|burn|monthly[_ -]?net[_ -]?burn|cash(?:[_ -]?balance)?|"
    r"runway|actual[_ -]?customers?|customer[_ -]?count|churn|retention|cac|margin|"
    r"contracts?|contract[_ -]?register|invoices?|invoice[_ -]?register|bank(?:[_ -]?data)?)\b"
)
_LOCAL_OR_FILE_RE = re.compile(
    r"(?i)(?:[a-z]:\\[^\s]+|/(?:home|users|tmp|var|mnt)/[^\s]+|\\\\[^\s]+|"
    r"\b[^\s\\/]+\.(?:pdf|docx?|xlsx?|csv|pptx?|txt|md)\b)"
)
_EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")
_PROMPT_RE = re.compile(r"(?i)\b(?:begin prompt|system prompt|ignore prior instructions)\b")
_NUMBER_RE = re.compile(r"\b\d{2,}\b")
_SECRET_TOKEN_RE = re.compile(r"(?i)\bsk-[a-z0-9][a-z0-9_-]{2,}\b")
_SENSITIVE_URL_QUERY_RE = re.compile(
    r"(?i)(?:^|[&;])(api[_-]?key|access[_-]?token|authorization|auth[_-]?token|secret|token)="
)


@dataclass(frozen=True)
class PublicResearchProviderResult:
    entries: tuple[dict[str, object], ...]
    market_snapshot: StartupMarketResearchSnapshot | None = None


class CaseResearchJobService:
    def __init__(
        self,
        *,
        case_repository: Any,
        plan_repository: Any,
        job_repository: Any,
        public_benchmark_repository: Any | None,
        scenario_repository: Any | None,
        research_provider: Any | None = None,
        research_providers: Mapping[RequestedResearchAcquisitionMode, Any] | None = None,
        acquisition_mode: ResearchAcquisitionMode | None = None,
        profile_repository: Any | None = None,
        market_research_service: StartupMarketResearchService | None = None,
        clock: Any | None = None,
    ) -> None:
        self._cases = case_repository
        self._plans = plan_repository
        self._jobs = job_repository
        self._public_benchmarks = public_benchmark_repository
        self._scenarios = scenario_repository
        self._profiles = profile_repository
        self._market_research_service = market_research_service or StartupMarketResearchService(
            clock=clock
        )
        providers: dict[RequestedResearchAcquisitionMode, Any] = {
            mode: provider
            for mode, provider in (research_providers or {}).items()
            if provider is not None
        }
        if research_provider is not None and acquisition_mode is None:
            raise ValueError("research_acquisition_mode_required")
        if research_provider is not None:
            if acquisition_mode == "provider_unconfigured":
                raise ValueError("research_acquisition_mode_required")
            providers[cast(RequestedResearchAcquisitionMode, acquisition_mode)] = research_provider
        if (
            research_provider is None
            and not providers
            and acquisition_mode not in (None, "provider_unconfigured")
        ):
            raise ValueError("research_provider_required_for_acquisition_mode")
        self._providers = providers
        self._clock = clock or (lambda: datetime.now(UTC))

    def available_acquisition_modes(self) -> dict[str, tuple[str, ...] | str]:
        ordered_modes: tuple[RequestedResearchAcquisitionMode, ...] = (
            "live_public_research",
            "deterministic_offline_fixture",
        )
        available = tuple(mode for mode in ordered_modes if mode in self._providers)
        unavailable = tuple(mode for mode in ordered_modes if mode not in self._providers)
        default = available[0] if available else unavailable[0]
        return {"available": available, "unavailable": unavailable, "default": default}

    def prepare_plan(
        self,
        case_id: UUID,
        request: PrepareResearchPlanRequest,
    ) -> ResearchPlanResponse:
        case = self._case(case_id)
        revision = int(case.data_revision)
        if request.expected_case_revision != revision:
            raise StartupGateConflict("stale_research_plan")
        focus = _normalize_key(request.focus)
        private_value = _normalize_key(request.requested_private_value or "")
        if _is_private_metric_request(focus) or _is_private_metric_request(private_value):
            raise StartupValidationError("private_public_research_rejected")
        if focus not in _ALLOWED_PUBLIC_FOCUS:
            raise StartupValidationError("public_research_focus_not_supported")
        now = self._clock()
        query_previews = self._research_query_previews(
            case_id=case_id,
            revision=revision,
            focus=focus,
        )
        plan_hash = _plan_hash(
            case_id=case_id,
            revision=revision,
            focus=focus,
            query_previews=query_previews,
        )
        plan = CaseResearchPlan(
            plan_id=uuid5(NAMESPACE_URL, f"research-plan:{case_id}:{revision}:{plan_hash}"),
            case_id=case_id,
            data_revision=revision,
            focus_key=focus,
            intent=f"public {focus.replace('_', ' ')} research",
            plan_hash=plan_hash,
            query_previews=query_previews,
            manual_only_keys=_MANUAL_ONLY_KEYS,
            consent_text=(
                "Consent required: run public web research only for external context; "
                "do not send private founder metrics or uploaded documents."
            ),
            created_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        saved = self._plans.save(
            plan,
            expected_revision=revision,
            idempotency_key=f"research-plan:{plan_hash}",
        )
        return _plan_response(saved)

    def queue_job(
        self,
        case_id: UUID,
        request: QueueResearchJobRequest,
    ) -> ResearchJobResponse:
        requested_mode = self._requested_acquisition_mode(request)
        fingerprint = _job_request_fingerprint(request, acquisition_mode=requested_mode)
        existing = _get_by_idempotency(
            self._jobs,
            case_id,
            f"{request.idempotency_key}:result",
        ) or _get_by_idempotency(self._jobs, case_id, request.idempotency_key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise StartupGateConflict("idempotency_key_conflict")
            return _job_response(existing)
        if not request.consent_public_research:
            raise StartupValidationError("public_research_consent_required")
        plan = self._load_valid_plan(case_id, request)
        cached = self._cached_completed_live_job(
            case_id,
            plan,
            requested_mode=requested_mode,
            retry_of_job_id=request.retry_of_job_id,
        )
        if cached is not None:
            return _job_response(
                self._save_cached_live_job(
                    case_id,
                    plan,
                    request,
                    cached=cached,
                    fingerprint=fingerprint,
                )
            )
        running = [
            job
            for job in self._jobs.list_for_case(case_id)
            if job.plan_hash == plan.plan_hash and job.status == "running"
        ]
        if running:
            raise StartupGateConflict("research_job_already_running")
        provider = self._providers.get(requested_mode)
        if provider is None:
            return _job_response(
                self._save_job(
                    case_id,
                    plan,
                    request,
                    status="deferred",
                    reason="provider_unconfigured",
                    fingerprint=fingerprint,
                    acquisition_mode="provider_unconfigured",
                )
            )

        running_job = self._save_job(
            case_id,
            plan,
            request,
            status="running",
            reason=None,
            fingerprint=fingerprint,
            acquisition_mode=requested_mode,
        )
        try:
            provider_result = provider.collect(
                self._collection_plan(
                    plan,
                    acquisition_mode=requested_mode,
                    research_job_id=running_job.job_id,
                )
            )
        except StartupGateConflict:
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary must fail closed
            provider_reason = _provider_failure_reason(exc)
            failed = running_job.model_copy(
                update={
                    "status": "failed",
                    "reason": provider_reason,
                    "fail_reason": _sanitize_text(str(exc)),
                    "updated_at": self._clock(),
                }
            )
            return _job_response(
                self._jobs.save(
                    failed,
                    expected_revision=plan.data_revision,
                    idempotency_key=f"{request.idempotency_key}:result",
                )
            )
        accepted, rejected = _validated_entries(
            provider_result,
            case_id=case_id,
            revision=plan.data_revision,
        )
        live_snapshot = _live_market_research_snapshot(provider_result)
        has_live_market_sources = (
            requested_mode == "live_public_research"
            and live_snapshot is not None
            and bool(live_snapshot.sources)
        )
        current_case = self._case(case_id)
        current_revision = int(current_case.data_revision)
        if current_revision != plan.data_revision:
            stale_rejections = tuple(
                _rejected_entry(
                    "stale_research_plan",
                    entry.model_dump(mode="python"),
                    input_key=entry.input_key,
                    provenance=entry.provenance.value,
                )
                for entry in accepted
            )
            deferred = running_job.model_copy(
                update={
                    "data_revision": current_revision,
                    "status": "deferred",
                    "reason": "stale_research_plan",
                    "accepted_entries": (),
                    "rejected_entries": (*rejected, *stale_rejections),
                    "manual_only_keys": plan.manual_only_keys,
                    "old_revision": plan.data_revision,
                    "new_revision": current_revision,
                    "result_summary": "Research plan became stale before public benchmark acceptance.",
                    "updated_at": self._clock(),
                }
            )
            return _job_response(
                self._jobs.save(
                    deferred,
                    expected_revision=current_revision,
                    idempotency_key=f"{request.idempotency_key}:result",
                )
            )
        stale_scenario_ids = _stale_scenario_ids(self._scenarios, case_id, plan.data_revision)
        changed_refs = self._persist_public_benchmarks(accepted, expected_revision=plan.data_revision)
        useful_research = bool(accepted) or has_live_market_sources
        status = (
            "completed"
            if useful_research and not rejected
            else "partial"
            if useful_research
            else "deferred"
        )
        completion_reason: str | None = (
            None if useful_research else "no_eligible_public_benchmarks"
        )
        old_revision = plan.data_revision
        new_revision = plan.data_revision
        case_advanced = False
        advance_revision = bool(changed_refs) or has_live_market_sources
        try:
            if advance_revision and hasattr(self._cases, "advance_data_revision"):
                updated_case = current_case.model_copy(update={"data_revision": plan.data_revision + 1})
                self._cases.advance_data_revision(
                    case_id,
                    expected_revision=plan.data_revision,
                    updated_case=updated_case,
                )
                new_revision = plan.data_revision + 1
                case_advanced = True
        except Exception as exc:  # noqa: BLE001 - cross-repository commit boundary
            self._rollback_public_benchmarks(case_id, changed_refs)
            failed = running_job.model_copy(
                update={
                    "status": "failed",
                    "reason": "public_benchmark_commit_failed",
                    "fail_reason": _sanitize_text(str(exc)),
                    "accepted_entries": (),
                    "rejected_entries": rejected,
                    "manual_only_keys": plan.manual_only_keys,
                    "old_revision": old_revision,
                    "new_revision": old_revision,
                    "source_refs": (),
                    "result_summary": "Public benchmark commit failed before case revision advanced.",
                    "updated_at": self._clock(),
                }
            )
            return _job_response(
                self._jobs.save(
                    failed,
                    expected_revision=old_revision,
                    idempotency_key=f"{request.idempotency_key}:result",
                )
            )
        normalized_live_snapshot = (
            _normalize_live_market_snapshot(
                live_snapshot,
                case_id=case_id,
                data_revision=new_revision,
            )
            if has_live_market_sources and live_snapshot is not None
            else None
        )
        completed = running_job.model_copy(
            update={
                "data_revision": new_revision,
                "status": status,
                    "reason": completion_reason,
                "accepted_entries": accepted,
                "rejected_entries": rejected,
                "citations": _research_citations(accepted, normalized_live_snapshot),
                "manual_only_keys": plan.manual_only_keys,
                "changed_blocks": _changed_blocks(
                    changed_refs=changed_refs,
                    has_live_market_sources=has_live_market_sources,
                ),
                "stale_scenario_ids": stale_scenario_ids if advance_revision else (),
                "old_revision": old_revision,
                "new_revision": new_revision,
                "source_refs": _source_refs(changed_refs, normalized_live_snapshot),
                "live_market_research_snapshot": normalized_live_snapshot,
                "result_summary": (
                    "Public market research sources accepted."
                    if useful_research
                    else "No eligible public benchmarks accepted."
                ),
                "updated_at": self._clock(),
            }
        )
        try:
            saved_completed = self._jobs.save(
                completed,
                expected_revision=new_revision,
                idempotency_key=f"{request.idempotency_key}:result",
            )
        except Exception:
            self._rollback_public_benchmarks(case_id, changed_refs)
            if case_advanced:
                self._restore_case_revision(
                    case_id,
                    current_case=current_case,
                    old_revision=old_revision,
                    new_revision=new_revision,
                )
            raise
        return _job_response(saved_completed)

    def get_job(self, case_id: UUID, job_id: UUID) -> ResearchJobResponse:
        try:
            return _job_response(self._jobs.get_for_case(case_id, job_id))
        except KeyError as exc:
            raise StartupNotFound("research_job_not_found") from exc

    def get_internal_job(self, case_id: UUID, job_id: UUID) -> CaseResearchJob:
        try:
            return cast(CaseResearchJob, self._jobs.get_for_case(case_id, job_id))
        except KeyError as exc:
            raise StartupNotFound("research_job_not_found") from exc

    def get_job_by_idempotency(
        self,
        case_id: UUID,
        idempotency_key: str,
    ) -> ResearchJobResponse | None:
        existing = _get_by_idempotency(
            self._jobs,
            case_id,
            f"{idempotency_key}:result",
        ) or _get_by_idempotency(self._jobs, case_id, idempotency_key)
        return None if existing is None else _job_response(existing)

    def _load_valid_plan(
        self,
        case_id: UUID,
        request: QueueResearchJobRequest,
    ) -> CaseResearchPlan:
        case = self._case(case_id)
        revision = int(case.data_revision)
        if request.expected_case_revision != revision:
            raise StartupGateConflict("stale_research_plan")
        try:
            plan = self._plans.get_for_case(case_id, request.plan_id)
        except KeyError as exc:
            raise StartupNotFound("research_plan_not_found") from exc
        now = self._clock()
        if (
            plan.plan_hash != request.plan_hash
            or plan.data_revision != revision
            or plan.expires_at <= now
        ):
            raise StartupGateConflict("stale_research_plan")
        return cast(CaseResearchPlan, plan)

    def _requested_acquisition_mode(
        self,
        request: QueueResearchJobRequest,
    ) -> RequestedResearchAcquisitionMode:
        if request.acquisition_mode is not None:
            return request.acquisition_mode
        default = self.available_acquisition_modes()["default"]
        if default in {"deterministic_offline_fixture", "live_public_research"}:
            return cast(RequestedResearchAcquisitionMode, default)
        return "live_public_research"

    def _save_job(
        self,
        case_id: UUID,
        plan: CaseResearchPlan,
        request: QueueResearchJobRequest,
        *,
        status: str,
        reason: str | None,
        fingerprint: str,
        acquisition_mode: ResearchAcquisitionMode,
        requested_acquisition_mode: RequestedResearchAcquisitionMode | None = None,
    ) -> CaseResearchJob:
        requested = requested_acquisition_mode or self._requested_acquisition_mode(request)
        job = CaseResearchJob(
            job_id=uuid4(),
            case_id=case_id,
            data_revision=plan.data_revision,
            focus_key=plan.focus_key,
            status=cast(Any, status),
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            request_fingerprint=fingerprint,
            reason=reason,
            acquisition_mode=acquisition_mode,
            requested_acquisition_mode=requested,
            selected_acquisition_mode=acquisition_mode,
            retry_of_job_id=request.retry_of_job_id,
            updated_at=self._clock(),
            manual_only_keys=plan.manual_only_keys,
            old_revision=plan.data_revision,
            new_revision=plan.data_revision,
        )
        return cast(
            CaseResearchJob,
            self._jobs.save(
                job,
                expected_revision=plan.data_revision,
                idempotency_key=request.idempotency_key,
            ),
        )

    def _cached_completed_live_job(
        self,
        case_id: UUID,
        plan: CaseResearchPlan,
        *,
        requested_mode: RequestedResearchAcquisitionMode,
        retry_of_job_id: UUID | None,
    ) -> CaseResearchJob | None:
        if requested_mode != "live_public_research" or retry_of_job_id is not None:
            return None
        current_revision = int(self._case(case_id).data_revision)
        candidates: list[CaseResearchJob] = [
            job
            for job in self._jobs.list_for_case(case_id)
            if job.focus_key == plan.focus_key
            and job.status in {"completed", "partial"}
            and job.acquisition_mode == "live_public_research"
            and job.requested_acquisition_mode == "live_public_research"
            and job.new_revision == current_revision
            and _job_has_public_research_result(job)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda job: job.updated_at)

    def _save_cached_live_job(
        self,
        case_id: UUID,
        plan: CaseResearchPlan,
        request: QueueResearchJobRequest,
        *,
        cached: CaseResearchJob,
        fingerprint: str,
    ) -> CaseResearchJob:
        replay = self._save_job(
            case_id,
            plan,
            request,
            status="running",
            reason=None,
            fingerprint=fingerprint,
            acquisition_mode="live_public_research",
        )
        completed = replay.model_copy(
            update={
                "status": cached.status,
                "reason": "cached_completed_research",
                "fail_reason": None,
                "accepted_entries": cached.accepted_entries,
                "rejected_entries": cached.rejected_entries,
                "citations": cached.citations,
                "manual_only_keys": plan.manual_only_keys,
                "changed_blocks": (),
                "stale_scenario_ids": (),
                "source_refs": cached.source_refs,
                "live_market_research_snapshot": cached.live_market_research_snapshot,
                "old_revision": plan.data_revision,
                "new_revision": plan.data_revision,
                "result_summary": (
                    "Reused saved live public research for the current case revision "
                    "without a new provider call."
                ),
                "updated_at": self._clock(),
            }
        )
        return cast(
            CaseResearchJob,
            self._jobs.save(
                completed,
                expected_revision=plan.data_revision,
                idempotency_key=f"{request.idempotency_key}:result",
            ),
        )

    def _persist_public_benchmarks(
        self,
        entries: tuple[PublicBenchmarkEntry, ...],
        *,
        expected_revision: int,
    ) -> tuple[UUID, ...]:
        if self._public_benchmarks is None:
            return ()
        saved_refs: list[UUID] = []
        try:
            for entry in entries:
                lower = entry.range_low if entry.range_low is not None else entry.value
                upper = entry.range_high if entry.range_high is not None else entry.value
                if lower is None or upper is None:
                    continue
                scenario_input = ScenarioInput(
                    input_id=entry.entry_id,
                    case_id=entry.case_id,
                    data_revision=entry.data_revision,
                    input_key=entry.input_key,
                    value_range=ScenarioRange(lower=lower, upper=upper),
                    unit=entry.unit,
                    period=entry.period,
                    provenance=CaseValueKind.PUBLIC_BENCHMARK,
                    source_refs=entry.source_refs,
                    dependency_refs=(),
                    confidence=entry.confidence,
                    rationale=entry.rationale,
                    validation_plan=entry.validation_plan,
                    what_would_confirm="Validate against case-specific source evidence before using as source_fact.",
                    acceptance="accepted",
                )
                saved = self._public_benchmarks.save(
                    scenario_input,
                    expected_revision=expected_revision,
                    idempotency_key=f"public-benchmark:{entry.entry_id}",
                )
                saved_refs.append(saved.input_id)
        except Exception:
            self._rollback_public_benchmarks(
                entries[0].case_id if entries else UUID(int=0),
                tuple(saved_refs),
            )
            raise
        return tuple(saved_refs)

    def _case(self, case_id: UUID) -> DueDiligenceCase:
        try:
            return cast(DueDiligenceCase, self._cases.get(case_id))
        except KeyError as exc:
            raise StartupNotFound("case_not_found") from exc

    def _rollback_public_benchmarks(
        self,
        case_id: UUID,
        input_ids: tuple[UUID, ...],
    ) -> None:
        if self._public_benchmarks is None:
            return
        deleter = getattr(self._public_benchmarks, "delete_for_case", None)
        if not callable(deleter):
            raise TypeError("public_benchmark_rollback_unavailable")
        for input_id in input_ids:
            deleter(case_id, input_id)

    def _restore_case_revision(
        self,
        case_id: UUID,
        *,
        current_case: DueDiligenceCase,
        old_revision: int,
        new_revision: int,
    ) -> None:
        restorer = getattr(self._cases, "restore_data_revision", None)
        if not callable(restorer):
            raise TypeError("case_revision_restore_unavailable")
        restored_case = current_case.model_copy(update={"data_revision": old_revision})
        restorer(
            case_id,
            expected_revision=new_revision,
            restored_case=restored_case,
        )

    def _research_query_previews(
        self,
        *,
        case_id: UUID,
        revision: int,
        focus: str,
    ) -> tuple[str, ...]:
        provider_default = self.available_acquisition_modes()["default"]
        if provider_default != "live_public_research":
            return _sanitized_query_previews(focus=focus)
        profile = _profile_for_research_plan(self._profiles, case_id, revision)
        if profile is None:
            return _sanitized_query_previews(focus=focus)
        result = self._market_research_service.build_research_plan(
            profile,
            source_mode=StartupResearchSourceMode.LIVE,
            public_focus=focus,
            public_topic=focus.replace("_", " "),
        )
        return result.plan.queries or _sanitized_query_previews(focus=focus)

    def _collection_plan(
        self,
        plan: CaseResearchPlan,
        *,
        acquisition_mode: RequestedResearchAcquisitionMode,
        research_job_id: UUID,
    ) -> CaseResearchPlan:
        if acquisition_mode != "live_public_research":
            return plan
        query_previews = self._research_query_previews(
            case_id=plan.case_id,
            revision=plan.data_revision,
            focus=plan.focus_key,
        )
        return plan.model_copy(
            update={
                "query_previews": query_previews,
                "research_job_id": research_job_id,
            }
        )


class StartupResearchPortBenchmarkProvider:
    """Adapter from the shared startup research port into the Task6 job provider seam."""

    def __init__(self, research_port: Any) -> None:
        self._research_port = research_port

    def collect(self, plan: CaseResearchPlan) -> PublicResearchProviderResult:
        port_plan = StartupResearchPlan(
            case_id=plan.case_id,
            research_job_id=plan.research_job_id,
            source_mode=StartupResearchSourceMode.LIVE,
            queries=plan.query_previews,
            max_queries=max(1, min(3, len(plan.query_previews))),
        )
        snapshot = self._research_port.collect(port_plan)
        entries: list[dict[str, object]] = []
        used_source_refs: set[object] = set()
        for candidate in tuple(getattr(snapshot, "public_benchmark_candidates", ()))[:5]:
            input_key = str(getattr(candidate, "input_key", ""))
            source_ref = getattr(candidate, "source_ref", None)
            provenance = str(getattr(candidate, "provenance", ""))
            publication_date = getattr(candidate, "publication_date", None)
            if provenance != CaseValueKind.PUBLIC_BENCHMARK.value:
                entries.append(
                    {
                        "_reject_reason": "provenance_not_public_benchmark",
                        "input_key": input_key,
                        "url": str(getattr(candidate, "source_url", "")),
                        "source_class": str(getattr(candidate, "source_class", "public_benchmark")),
                        "provenance": provenance,
                    }
                )
                continue
            if input_key != _benchmark_input_key(plan.focus_key):
                entries.append(
                    {
                        "_reject_reason": "focus_mismatch",
                        "input_key": input_key,
                        "url": str(getattr(candidate, "source_url", "")),
                        "source_class": str(getattr(candidate, "source_class", "public_benchmark")),
                    }
                )
                continue
            used_source_refs.add(source_ref)
            entries.append(
                {
                    "input_key": input_key,
                    "provenance": provenance,
                    "url": str(getattr(candidate, "source_url", "")),
                    "publisher": str(getattr(candidate, "publisher", "")),
                    "publication_date": None if publication_date is None else str(publication_date),
                    "retrieval_date": str(getattr(candidate, "retrieval_date", "")),
                    "as_of": str(getattr(candidate, "as_of", "")),
                    "source_class": str(getattr(candidate, "source_class", "")),
                    "confidence": str(getattr(candidate, "confidence", "")),
                    "value": getattr(candidate, "value", None),
                    "range_low": getattr(candidate, "range_low", None),
                    "range_high": getattr(candidate, "range_high", None),
                    "unit": str(getattr(candidate, "unit", "")),
                    "period": str(getattr(candidate, "period", "")),
                    "formula": str(getattr(candidate, "formula", "")),
                    "dependencies": tuple(getattr(candidate, "dependencies", ())),
                    "validation_plan": str(getattr(candidate, "validation_plan", "")),
                    "source_refs": (source_ref,),
                    "rationale": str(getattr(candidate, "rationale", "")),
                }
            )
        if not isinstance(snapshot, StartupMarketResearchSnapshot):
            for source in tuple(getattr(snapshot, "sources", ()))[:5]:
                source_id = getattr(source, "source_id", uuid4())
                if source_id in used_source_refs:
                    continue
                entries.append(
                    {
                        "_reject_reason": "non_quantitative_source",
                        "input_key": _benchmark_input_key(plan.focus_key),
                        "url": str(getattr(source, "source_url", "")),
                        "source_class": "public_research_source",
                        "source_id": str(source_id),
                    }
                )
        return PublicResearchProviderResult(
            entries=tuple(entries),
            market_snapshot=(
                snapshot if isinstance(snapshot, StartupMarketResearchSnapshot) else None
            ),
        )


def _benchmark_input_key(focus: str) -> str:
    if focus == "public_pricing_analogs":
        return "monthly_price"
    if focus in {"channels", "unit_economics_benchmarks"}:
        return "acquisition_spend"
    return "arpa"


def mark_running_jobs_deferred(repository: Any, *, clock: Any | None = None) -> None:
    """Best-effort startup repair for interrupted local research jobs."""

    now = (clock or (lambda: datetime.now(UTC)))()
    cases: set[UUID] = set()
    state_reader = getattr(repository, "list_all", None)
    if callable(state_reader):
        jobs = state_reader()
    else:
        jobs = ()
    for job in jobs:
        if getattr(job, "status", None) == "running":
            cases.add(job.case_id)
            repository.save(
                job.model_copy(
                    update={
                        "status": "deferred",
                        "reason": "research_interrupted",
                        "updated_at": now,
                    }
                ),
                expected_revision=job.data_revision,
                idempotency_key=f"interrupted:{job.job_id}",
            )


def _validated_entries(
    provider_result: object,
    *,
    case_id: UUID,
    revision: int,
) -> tuple[tuple[PublicBenchmarkEntry, ...], tuple[RejectedResearchEntry, ...]]:
    raw_entries = getattr(provider_result, "entries", provider_result)
    if raw_entries is None:
        return (), ()
    accepted: list[PublicBenchmarkEntry] = []
    rejected: list[RejectedResearchEntry] = []
    for raw in raw_entries if isinstance(raw_entries, list | tuple) else ():
        try:
            payload = raw.model_dump(mode="python") if hasattr(raw, "model_dump") else dict(raw)
        except Exception:  # noqa: BLE001
            rejected.append(_rejected_entry("malformed_entry", raw))
            continue
        reject_reason = payload.get("_reject_reason")
        if isinstance(reject_reason, str) and reject_reason:
            rejected.append(
                _rejected_entry(
                    reject_reason,
                    payload,
                    input_key=payload.get("input_key"),
                    provenance=payload.get("provenance"),
                )
            )
            continue
        raw_provenance = str(payload.get("provenance") or "")
        if raw_provenance != CaseValueKind.PUBLIC_BENCHMARK.value:
            rejected.append(
                _rejected_entry(
                    "provenance_not_public_benchmark",
                    payload,
                    input_key=payload.get("input_key"),
                    provenance=raw_provenance,
                )
            )
            continue
        try:
            entry = PublicBenchmarkEntry.model_validate(
                {
                    **payload,
                    "entry_id": uuid4(),
                    "case_id": case_id,
                    "data_revision": revision,
                    "provenance": CaseValueKind.PUBLIC_BENCHMARK,
                }
            )
            if not _is_safe_public_url(entry.url):
                rejected.append(
                    _rejected_entry(
                        "invalid_citation_url",
                        payload,
                        input_key=entry.input_key,
                        provenance=entry.provenance.value,
                    )
                )
            else:
                accepted.append(entry)
        except Exception:  # noqa: BLE001
            rejected.append(_rejected_entry("invalid_benchmark_entry", payload))
    return tuple(accepted), tuple(rejected)


def _live_market_research_snapshot(provider_result: object) -> StartupMarketResearchSnapshot | None:
    snapshot = getattr(provider_result, "market_snapshot", None)
    return snapshot if isinstance(snapshot, StartupMarketResearchSnapshot) else None


def _normalize_live_market_snapshot(
    snapshot: StartupMarketResearchSnapshot,
    *,
    case_id: UUID,
    data_revision: int,
) -> StartupMarketResearchSnapshot:
    return _normalize_live_public_research_snapshot(
        snapshot,
        case_id=case_id,
        data_revision=data_revision,
    )


def _normalize_live_public_research_snapshot(
    snapshot: StartupMarketResearchSnapshot,
    *,
    case_id: UUID,
    data_revision: int,
) -> StartupMarketResearchSnapshot:
    return StartupMarketResearchSnapshot.build(
        case_id=case_id,
        as_of=snapshot.as_of,
        source_mode=StartupResearchSourceMode.LIVE,
        research_id=snapshot.research_id,
        competitors=_normalize_live_public_research_competitors(snapshot.competitors),
        sources=_normalize_live_public_research_sources(snapshot.sources),
        sentiment_signals=snapshot.sentiment_signals,
        assumptions=_normalize_live_public_research_assumptions(snapshot.assumptions),
        sizing=_normalize_live_public_research_sizing(snapshot.sizing),
        labels=(*snapshot.labels, "live_public_research"),
        data_revision=data_revision,
        public_benchmark_candidates=snapshot.public_benchmark_candidates,
    )


def _normalize_live_public_research_sources(
    sources: tuple[StartupResearchSource, ...],
) -> tuple[StartupResearchSource, ...]:
    return tuple(
        source.model_copy(
            update={
                "source_mode": StartupResearchSourceMode.LIVE,
                "status": StartupResearchSourceStatus.INFERENCE,
                "supports_primary_financial_metrics": False,
            }
        )
        for source in sources
    )


_LIVE_PUBLIC_RESEARCH_REASON_CODE = "live_public_research_context"


def _normalize_live_public_research_competitors(
    competitors: tuple[StartupCompetitor, ...],
) -> tuple[StartupCompetitor, ...]:
    return tuple(
        StartupCompetitor.model_validate(
            competitor.model_dump(mode="python")
            | {
                "status": StartupResearchSourceStatus.INFERENCE,
                "reason_code": competitor.reason_code
                or _LIVE_PUBLIC_RESEARCH_REASON_CODE,
            }
        )
        for competitor in competitors
    )


def _normalize_live_public_research_assumptions(
    assumptions: tuple[MarketSizingAssumption, ...],
) -> tuple[MarketSizingAssumption, ...]:
    return tuple(
        MarketSizingAssumption.model_validate(
            assumption.model_dump(mode="python")
            | {
                "source_mode": StartupResearchSourceMode.LIVE,
                "status": StartupResearchSourceStatus.INFERENCE,
                "reason_code": assumption.reason_code or _LIVE_PUBLIC_RESEARCH_REASON_CODE,
            }
        )
        for assumption in assumptions
    )


def _normalize_live_public_research_sizing(
    sizing: StartupMarketSizing | None,
) -> StartupMarketSizing | None:
    if sizing is None:
        return None
    tam = _normalize_live_public_research_estimate(sizing.tam)
    sam = _normalize_live_public_research_estimate(sizing.sam)
    som = _normalize_live_public_research_estimate(sizing.som)
    if tam is None or sam is None or som is None:
        return None
    try:
        return StartupMarketSizing(
            tam=tam,
            sam=sam,
            som=som,
        )
    except ValueError:
        return None


def _normalize_live_public_research_estimate(
    estimate: MarketSizingEstimate,
) -> MarketSizingEstimate | None:
    if estimate.value is not None and not estimate.assumption_refs:
        return None
    return MarketSizingEstimate.model_validate(
        estimate.model_dump(mode="python")
        | {
            "source_mode": StartupResearchSourceMode.LIVE,
            "level": StartupResearchSourceStatus.INFERENCE,
        }
    )


def _research_citations(
    accepted: tuple[PublicBenchmarkEntry, ...],
    live_snapshot: StartupMarketResearchSnapshot | None,
) -> tuple[str, ...]:
    citations: list[str] = [entry.url for entry in accepted]
    if live_snapshot is not None:
        citations.extend(source.source_url.unicode_string() for source in live_snapshot.sources)
    return tuple(dict.fromkeys(citations))


def _source_refs(
    changed_refs: tuple[UUID, ...],
    live_snapshot: StartupMarketResearchSnapshot | None,
) -> tuple[UUID, ...]:
    refs: list[UUID] = [*changed_refs]
    if live_snapshot is not None:
        refs.extend(source.source_id for source in live_snapshot.sources)
    return tuple(dict.fromkeys(refs))


def _changed_blocks(
    *,
    changed_refs: tuple[UUID, ...],
    has_live_market_sources: bool,
) -> tuple[str, ...]:
    blocks: list[str] = []
    if changed_refs:
        blocks.append("public_benchmarks")
    if has_live_market_sources:
        blocks.append("market_research")
    if changed_refs or has_live_market_sources:
        blocks.append("scenarios")
    return tuple(blocks)


def _profile_for_research_plan(
    repository: Any | None,
    case_id: UUID,
    revision: int,
) -> Any | None:
    if repository is None:
        return None
    stage_getter = getattr(repository, "get_for_stage", None)
    if callable(stage_getter):
        try:
            profile = stage_getter(
                case_id,
                revision,
                StartupProfileAnalysisStage.PRIMARY,
            )
        except KeyError:
            return None
        except Exception as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        _validate_research_plan_profile(profile, case_id=case_id, revision=revision)
        return profile
    current_getter = getattr(repository, "get_current", None)
    if callable(current_getter):
        try:
            profile = current_getter(case_id)
        except KeyError:
            return None
        except Exception as exc:
            raise StartupGateConflict("research_profile_projection_unavailable") from exc
        _validate_research_plan_profile(profile, case_id=case_id, revision=revision)
        return profile
    return None


def _validate_research_plan_profile(profile: object, *, case_id: UUID, revision: int) -> None:
    if getattr(profile, "case_id", None) != case_id or getattr(profile, "data_revision", None) != revision:
        raise StartupGateConflict("research_profile_projection_unavailable")


def _is_safe_public_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and _SENSITIVE_URL_QUERY_RE.search(parsed.query) is None
    )


def _rejected_entry(
    reason_code: str,
    raw: object,
    *,
    input_key: object | None = None,
    provenance: object | None = None,
) -> RejectedResearchEntry:
    metadata: dict[str, str] = {}
    if isinstance(raw, dict):
        for key in ("url", "source_class", "confidence"):
            value = raw.get(key)
            if value is not None:
                metadata[key] = (
                    _sanitize_url_for_audit(str(value))
                    if key == "url"
                    else _sanitize_audit_text(str(value))
                )
        input_key = input_key if input_key is not None else raw.get("input_key")
        provenance = provenance if provenance is not None else raw.get("provenance")
    else:
        metadata["raw_type"] = type(raw).__name__
    return RejectedResearchEntry(
        rejected_id=uuid4(),
        reason_code=reason_code,
        input_key=_sanitize_audit_text(str(input_key)) if input_key is not None else None,
        provenance=_sanitize_audit_text(str(provenance)) if provenance is not None else None,
        metadata=metadata,
    )


def _plan_response(plan: CaseResearchPlan) -> ResearchPlanResponse:
    return ResearchPlanResponse(
        case_id=plan.case_id,
        data_revision=plan.data_revision,
        status=plan.status,
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        focus=plan.focus_key,
        query_previews=tuple(plan.query_previews),
        manual_only_keys=tuple(plan.manual_only_keys),
        consent_text=plan.consent_text,
        created_at=plan.created_at,
        expires_at=plan.expires_at,
    )


def _job_response(job: CaseResearchJob) -> ResearchJobResponse:
    return ResearchJobResponse(
        case_id=job.case_id,
        data_revision=job.data_revision,
        job_id=job.job_id,
        plan_id=job.plan_id,
        plan_hash=job.plan_hash,
        status=cast(Any, job.status),
        acquisition_mode=job.acquisition_mode,
        requested_acquisition_mode=job.requested_acquisition_mode,
        selected_acquisition_mode=job.selected_acquisition_mode,
        reason=job.reason or job.fail_reason,
        accepted_entries=tuple(_entry_projection(entry) for entry in job.accepted_entries),
        rejected_entries=tuple(_rejected_projection(entry) for entry in job.rejected_entries),
        citations=job.citations,
        manual_only_keys=job.manual_only_keys,
        changed_blocks=job.changed_blocks,
        stale_scenario_ids=job.stale_scenario_ids,
        old_revision=job.old_revision,
        new_revision=job.new_revision,
        source_refs=tuple(str(ref) for ref in job.source_refs),
        updated_at=job.updated_at,
    )


def _entry_projection(entry: PublicBenchmarkEntry) -> ResearchBenchmarkEntryProjection:
    return ResearchBenchmarkEntryProjection(
        entry_id=entry.entry_id,
        provenance=CaseValueKind.PUBLIC_BENCHMARK,
        input_key=entry.input_key,
        url=entry.url,
        publisher=entry.publisher,
        publication_date=entry.publication_date,
        retrieval_date=entry.retrieval_date,
        as_of=entry.as_of,
        source_class=entry.source_class,
        confidence=entry.confidence,
        value=None if entry.value is None else str(entry.value),
        range={
            "low": None if entry.range_low is None else str(entry.range_low),
            "high": None if entry.range_high is None else str(entry.range_high),
        },
        unit=entry.unit,
        period=entry.period,
        formula=entry.formula,
        dependencies=list(entry.dependencies),
        validation_plan=entry.validation_plan,
        source_refs=[str(ref) for ref in entry.source_refs],
    )


def _rejected_projection(entry: RejectedResearchEntry) -> ResearchRejectedEntryProjection:
    return ResearchRejectedEntryProjection(
        rejected_id=entry.rejected_id,
        reason_code=entry.reason_code,
        input_key=entry.input_key,
        provenance=entry.provenance,
        metadata=entry.metadata,
    )


def _get_by_idempotency(repository: Any, case_id: UUID, idempotency_key: str) -> CaseResearchJob | None:
    getter = getattr(repository, "get_by_idempotency", None)
    if getter is None:
        return None
    return cast(CaseResearchJob | None, getter(case_id, idempotency_key))


def _job_has_public_research_result(job: CaseResearchJob) -> bool:
    return bool(
        job.accepted_entries
        or job.citations
        or job.source_refs
        or (
            job.live_market_research_snapshot is not None
            and job.live_market_research_snapshot.sources
        )
    )


def _provider_failure_reason(exc: Exception) -> str:
    # Compatibility boundary: some provider adapters preserve the stable budget
    # code only in their sanitized exception text. The exact marker is covered by
    # a regression test and does not expose credentials or provider payloads.
    if isinstance(exc, BudgetExceeded) or "BUDGET_EXCEEDED" in str(exc):
        return "BUDGET_EXCEEDED"
    return "provider_failed"


def _job_request_fingerprint(
    request: QueueResearchJobRequest,
    *,
    acquisition_mode: RequestedResearchAcquisitionMode,
) -> str:
    payload = {
        "plan_id": str(request.plan_id),
        "plan_hash": request.plan_hash,
        "expected_case_revision": request.expected_case_revision,
        "consent_public_research": request.consent_public_research,
        "acquisition_mode": acquisition_mode,
        "retry_of_job_id": None if request.retry_of_job_id is None else str(request.retry_of_job_id),
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _plan_hash(
    *,
    case_id: UUID,
    revision: int,
    focus: str,
    query_previews: tuple[str, ...],
) -> str:
    payload = {
        "case_id": str(case_id),
        "revision": revision,
        "focus": focus,
        "queries": query_previews,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sanitized_query_previews(*, focus: str) -> tuple[str, ...]:
    if focus == "public_pricing_analogs":
        return (
            "Казахстан CRM SaaS тарифы цена тенге в месяц",
        )
    if focus == "unit_economics_benchmarks":
        return ("public unit economics benchmarks for comparable startup business models",)
    return (f"public {focus.replace('_', ' ')} context for comparable startup markets",)


def _sanitize_text(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    cleaned = _SECRET_TOKEN_RE.sub("[redacted-secret]", cleaned)
    cleaned = _LOCAL_OR_FILE_RE.sub("[redacted-local-or-file]", cleaned)
    cleaned = _EMAIL_RE.sub("[redacted-email]", cleaned)
    cleaned = _PROMPT_RE.sub("[redacted-prompt]", cleaned)
    cleaned = _PRIVATE_TEXT_RE.sub("[private_metric]", cleaned)
    cleaned = _NUMBER_RE.sub("[redacted-number]", cleaned)
    return cleaned or "public research"


def _sanitize_audit_text(value: str) -> str:
    cleaned = _sanitize_text(value)
    cleaned = "".join(char for char in cleaned if char.isprintable())
    return cleaned[:160]


def _sanitize_url_for_audit(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme == "https" and parsed.hostname:
        port = f":{parsed.port}" if parsed.port is not None else ""
        safe_path = parsed.path or "/"
        return _sanitize_audit_text(f"https://{parsed.hostname}{port}{safe_path}")
    return "[redacted-url]"


def _stale_scenario_ids(repository: Any | None, case_id: UUID, revision: int) -> tuple[UUID, ...]:
    if repository is None:
        return ()
    lister = getattr(repository, "list_for_case", None)
    if not callable(lister):
        return ()
    return tuple(
        scenario.scenario_set_id
        for scenario in lister(case_id)
        if getattr(scenario, "data_revision", None) == revision
    )


def _normalize_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _is_private_metric_request(value: str) -> bool:
    normalized = _normalize_key(value)
    return normalized in _PRIVATE_RESEARCH_KEYS


__all__ = [
    "CaseResearchJobService",
    "StartupResearchPortBenchmarkProvider",
    "mark_running_jobs_deferred",
]
