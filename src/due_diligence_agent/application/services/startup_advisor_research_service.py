from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any, Final
from uuid import UUID, uuid4

from due_diligence_agent.application.case_copilot_contracts import (
    PrepareResearchPlanRequest,
    QueueResearchJobRequest,
    ResearchJobResponse,
)
from due_diligence_agent.application.policies.budget import BudgetExceeded
from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
)
from due_diligence_agent.domain.startup.advisor import (
    AdvisorAnswer,
    AdvisorQuestion,
    AdvisorResearchDelta,
)
from due_diligence_agent.domain.startup.profile import StartupProfile
from due_diligence_agent.ports.startup_profiles import StartupProfileRepository
from due_diligence_agent.ports.startup_research import StartupResearchPort
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool

_PUBLIC_RESEARCH_TOPICS: Final[dict[str, str]] = {
    "icp": "public customer segment and market alternatives",
    "gtm_channel": "public go-to-market channel benchmarks",
    "competitors": "public competitor landscape",
    "competitor_landscape": "public competitor landscape",
}
_PUBLIC_RESEARCH_FOCUS: Final[dict[str, str]] = {
    "icp": "icp",
    "gtm_channel": "channels",
    "competitors": "competitors",
    "competitor_landscape": "competitors",
}
_OUTAGE_REASON_RU = "Публичный поиск временно недоступен."
_DURABLE_FLOW_REQUIRED_RU = (
    "Публичный поиск должен выполняться через durable research job flow."
)
_PUBLIC_RESEARCH_TIMEOUT_MS = 15_000


class StartupAdvisorResearchService:
    """Runs an optional public-only research side path for one advisor question."""

    def __init__(
        self,
        *,
        profile_repository: StartupProfileRepository,
        market_research_service: StartupMarketResearchService,
        live_research_port: StartupResearchPort | None,
        fallback_research_port: StartupResearchPort,
        case_research_service: Any | None = None,
        audit_spool: AuditSpool | None = None,
    ) -> None:
        self._profile_repository = profile_repository
        self._market_research_service = market_research_service
        self._live_research_port = live_research_port
        self._fallback_research_port = fallback_research_port
        self._case_research_service = case_research_service
        self._audit_spool = audit_spool

    def research(
        self,
        case_id: UUID,
        question: AdvisorQuestion,
        answer: AdvisorAnswer,
    ) -> AdvisorResearchDelta:
        started_at = perf_counter()
        if answer.answer_type != "public_research":
            return self._finish(
                case_id,
                AdvisorResearchDelta(
                    status="blocked",
                    summary_ru="Публичный поиск не запрошен.",
                    fail_reason_ru="Требуется режим публичного поиска.",
                ),
                started_at=started_at,
                attempt=0,
                error_code="research_mode_required",
            )
        if not answer.consent_public_research:
            return self._finish(
                case_id,
                AdvisorResearchDelta(
                    status="blocked",
                    summary_ru=(
                        "Публичный поиск заблокирован: требуется явное согласие."
                    ),
                    fail_reason_ru="Нет явного согласия на публичный поиск.",
                ),
                started_at=started_at,
                attempt=0,
                error_code="consent_required",
            )
        public_topic = _PUBLIC_RESEARCH_TOPICS.get(question.field_key)
        if public_topic is None:
            return self._finish(
                case_id,
                AdvisorResearchDelta(
                    status="blocked",
                    summary_ru=(
                        "Публичный поиск заблокирован: вопрос относится к внутренним данным."
                    ),
                    fail_reason_ru="Внутренние данные нельзя передавать в публичный поиск.",
                ),
                started_at=started_at,
                attempt=0,
                error_code="public_research_topic_blocked",
            )

        profile = self._profile_repository.get_current(case_id)
        if self._case_research_service is not None:
            return self._research_via_case_jobs(
                case_id,
                question,
                profile,
                started_at=started_at,
            )
        return self._finish(
            case_id,
            _deferred_delta(_DURABLE_FLOW_REQUIRED_RU),
            started_at=started_at,
            attempt=0,
            error_code="durable_research_flow_required",
        )

    def _research_via_case_jobs(
        self,
        case_id: UUID,
        question: AdvisorQuestion,
        profile: StartupProfile,
        *,
        started_at: float,
    ) -> AdvisorResearchDelta:
        case_research_service = self._case_research_service
        if case_research_service is None:
            return self._finish(
                case_id,
                _deferred_delta(_DURABLE_FLOW_REQUIRED_RU),
                started_at=started_at,
                attempt=0,
            )
        idempotency_key = _advisor_research_idempotency_key(
            case_id,
            question,
            profile.data_revision,
        )
        replay_getter = getattr(case_research_service, "get_job_by_idempotency", None)
        if callable(replay_getter):
            replayed = replay_getter(case_id, idempotency_key)
            if replayed is not None:
                return self._finish(
                    case_id,
                    _delta_from_case_job(replayed),
                    started_at=started_at,
                    attempt=0,
                )
        focus = _PUBLIC_RESEARCH_FOCUS.get(question.field_key, question.field_key)
        try:
            plan = case_research_service.prepare_plan(
                case_id,
                PrepareResearchPlanRequest(
                    focus=focus,
                    intent="Advisor public research request.",
                    expected_case_revision=profile.data_revision,
                ),
            )
            job = case_research_service.queue_job(
                case_id,
                QueueResearchJobRequest(
                    plan_id=plan.plan_id,
                    plan_hash=plan.plan_hash,
                    expected_case_revision=profile.data_revision,
                    idempotency_key=idempotency_key,
                    consent_public_research=True,
                ),
            )
        except BudgetExceeded:
            return self._finish(
                case_id,
                _deferred_delta(_OUTAGE_REASON_RU),
                started_at=started_at,
                attempt=1,
                error_code="budget_exceeded",
            )
        except TimeoutError:
            return self._finish(
                case_id,
                _deferred_delta(_OUTAGE_REASON_RU),
                started_at=started_at,
                attempt=1,
                error_code="provider_timeout",
            )
        except ValueError:
            return self._finish(
                case_id,
                _deferred_delta(_OUTAGE_REASON_RU),
                started_at=started_at,
                attempt=1,
                error_code="invalid_output",
            )
        except (RuntimeError, OSError):
            return self._finish(
                case_id,
                _deferred_delta(_OUTAGE_REASON_RU),
                started_at=started_at,
                attempt=1,
                error_code="provider_unavailable",
            )
        return self._finish(
            case_id,
            _delta_from_case_job(job),
            started_at=started_at,
            attempt=1,
            error_code=job.reason if job.status in {"deferred", "failed"} else None,
        )

    def _finish(
        self,
        case_id: UUID,
        delta: AdvisorResearchDelta,
        *,
        started_at: float,
        attempt: int,
        error_code: str | None = None,
    ) -> AdvisorResearchDelta:
        self._audit(
            case_id,
            status=delta.status,
            evidence_count=len(delta.source_ids),
            fallback_used=("cached_public_sources" if delta.fallback_used else "none"),
            latency_ms=max(0.0, (perf_counter() - started_at) * 1000),
            attempt=attempt,
            error_code=error_code,
        )
        return delta

    def _audit(
        self,
        case_id: UUID,
        *,
        status: str,
        evidence_count: int,
        fallback_used: str,
        latency_ms: float,
        attempt: int,
        error_code: str | None,
    ) -> None:
        if self._audit_spool is None:
            return
        attributes: dict[str, str | int | float | bool | None] = {
            "agent_role": "market",
            "attempt": attempt,
            "case_id": str(case_id),
            "evidence_count": evidence_count,
            "fallback_used": fallback_used,
            "latency_ms": latency_ms,
            "node_name": "advisor_public_research",
            "retry_count": 0,
            "status": status,
            "timeout_ms": _PUBLIC_RESEARCH_TIMEOUT_MS,
            "tool": "public_web_search",
        }
        if error_code is not None:
            attributes["error_code"] = error_code
        try:
            self._audit_spool.append(
                AuditEvent(
                    schema_version="audit_event@1",
                    event_id=str(uuid4()),
                    timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    run_id=f"startup-api-{case_id}",
                    correlation_id=str(case_id),
                    span_name="startup.advisor_public_research",
                    event_type="span",
                    attributes=attributes,
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return

    def _fallback_delta(
        self,
        profile: StartupProfile,
        reason_ru: str,
    ) -> AdvisorResearchDelta:
        try:
            frozen_plan = self._market_research_service.build_research_plan(profile).plan
            fallback = self._fallback_research_port.collect(frozen_plan)
            source_ids = tuple(source.source_id for source in fallback.sources[:5])
        except (RuntimeError, ValueError, OSError, KeyError):
            return _deferred_delta(reason_ru)
        if not source_ids:
            return _deferred_delta(reason_ru)
        return AdvisorResearchDelta(
            status="partial",
            summary_ru=(
                "Публичный поиск выполнен частично; использован сохранённый набор "
                "публичных источников."
            ),
            source_ids=source_ids,
            fallback_used=True,
            fail_reason_ru=reason_ru,
        )


def _advisor_research_idempotency_key(
    case_id: UUID,
    question: AdvisorQuestion,
    data_revision: int,
) -> str:
    digest = sha256(
        f"{case_id}:{data_revision}:{question.question_id}:{question.field_key}".encode()
    ).hexdigest()
    return f"advisor-public-research:{digest}"


def _delta_from_case_job(job: ResearchJobResponse) -> AdvisorResearchDelta:
    source_ids = tuple(
        parsed_ref
        for ref in job.source_refs
        if (parsed_ref := _parse_uuid(ref)) is not None
    )
    if job.changed_blocks:
        return AdvisorResearchDelta(
            status="deferred",
            summary_ru=(
                "Публичное исследование уже применено через durable Case Research job; "
                "legacy advisor recalculation не запускался."
            ),
            source_ids=source_ids,
            fail_reason_ru="case_research_job_mutated_case",
            fallback_used=False,
        )
    if job.status in {"completed", "partial"} and job.accepted_entries:
        return AdvisorResearchDelta(
            status="completed" if job.status == "completed" else "partial",
            summary_ru=(
                "Публичное исследование выполнено через durable research job. "
                f"Принято benchmark-записей: {len(job.accepted_entries)}; "
                f"отклонено: {len(job.rejected_entries)}."
            ),
            source_ids=source_ids,
            fallback_used=False,
        )
    return AdvisorResearchDelta(
        status="deferred",
        summary_ru="Публичное исследование отложено; durable research job не принял benchmark-записи.",
        fail_reason_ru=job.reason or "no_eligible_public_benchmarks",
        fallback_used=False,
    )


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _deferred_delta(reason_ru: str) -> AdvisorResearchDelta:
    return AdvisorResearchDelta(
        status="deferred",
        summary_ru="Публичный поиск отложен; результат пока недоступен.",
        source_ids=(),
        fallback_used=False,
        fail_reason_ru=reason_ru,
    )
