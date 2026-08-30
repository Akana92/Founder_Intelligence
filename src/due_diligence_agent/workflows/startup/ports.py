from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any, Protocol, TypedDict, cast
from uuid import UUID, uuid4

from due_diligence_agent.adapters.observability.metrics import MetricContract
from due_diligence_agent.application.services.claim_evidence_service import ClaimEvidenceService
from due_diligence_agent.application.services.report_service import (
    ReportFreezeRequired,
    ReportRendererUnavailable,
    ReportService,
)
from due_diligence_agent.application.services.founder_report_presentation_service import (
    FounderStartupReportPresentationService,
)
from due_diligence_agent.application.services.startup_report_service import (
    STARTUP_REPORT_SECTION_KEYS,
    StartupReportFreezeService,
    StartupReportProfileBindingError,
    StartupReportSnapshotBuilder,
    is_startup_report_snapshot,
    startup_canonical_snapshot_json,
)
from due_diligence_agent.application.services.startup_metric_service import StartupMetricService
from due_diligence_agent.application.services.startup_document_intelligence_service import (
    StartupDocumentIntelligenceService,
)
from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
)
from due_diligence_agent.application.services.startup_product_validation_service import (
    StartupProductValidationService,
)
from due_diligence_agent.application.services.startup_gtm_service import StartupGtmService
from due_diligence_agent.application.services.startup_readiness_service import (
    StartupReadinessService,
)
from due_diligence_agent.application.services.startup_reflexion_service import (
    StartupArbiterService,
    StartupCriticReview,
    StartupCriticService,
)
from due_diligence_agent.application.startup_cases import (
    CanonicalReportSnapshot,
    FreezeStatus,
    PdfStatus,
)
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import StartupClaim
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.metrics import MetricStatus
from due_diligence_agent.domain.metrics.startup import STARTUP_METRICS
from due_diligence_agent.domain.reports.models import ReportSnapshot
from due_diligence_agent.domain.startup.gtm import StartupGtmSnapshot
from due_diligence_agent.domain.startup.profile import StartupProfile
from due_diligence_agent.domain.startup.roles import StartupProductValidationSnapshot
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchSource,
    StartupResearchSourceMode,
)
from due_diligence_agent.domain.startup.readiness import (
    StartupMetricPack,
    StartupReadinessSnapshot,
)
from due_diligence_agent.ports.startup_research import StartupResearchPort
from due_diligence_agent.ports.tracing import AuditEvent, AuditSpool


_STARTUP_CHECKPOINT_ID_RE = re.compile(
    r"^startup-[A-Za-z0-9][A-Za-z0-9_.-]{0,63}-[0-9a-f]{12}$"
)
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_REPORT_TRACE_READ_LIMIT = 10_000


class StartupMetricWorkflowPort(Protocol):
    def calculate(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]: ...


class StartupDocumentIntelligenceWorkflowPort(Protocol):
    def analyze(
        self,
        *,
        case_id: str,
        data_revision: int,
        inventory_id: str,
        source_document_ids: list[str],
        artifact_ids: list[str],
        parsed_artifact_ids: list[str],
        evidence_fact_ids: list[str],
        startup_claim_ids: list[str],
        quarantine_reason_codes: list[str],
    ) -> dict[str, str | int]: ...


class StartupProductValidationWorkflowPort(Protocol):
    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        evidence_fact_ids: list[str],
        startup_claim_ids: list[str],
        claim_status_by_id: dict[str, str],
        contradiction_ids: list[str],
    ) -> dict[str, str | int]: ...


class StartupGtmWorkflowPort(Protocol):
    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        product_validation_snapshot_id: str,
        product_validation_snapshot_hash: str,
        product_validation_snapshot_revision: int,
        market_research_snapshot_id: str,
        market_research_snapshot_hash: str,
        market_research_snapshot_revision: int,
        evidence_fact_ids: list[str],
        finding_ids: list[str],
        contradiction_ids: list[str],
    ) -> dict[str, str | int]: ...


class StartupReadinessWorkflowPort(Protocol):
    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        metric_diagnostics: list[dict[str, Any]],
        calculation_ids: list[str],
    ) -> dict[str, str | int]: ...


class StartupMarketResearchWorkflowPort(Protocol):
    def research(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
    ) -> dict[str, str | int]: ...


class StartupClaimWorkflowPort(Protocol):
    def extract(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]: ...


class StartupEvidenceWorkflowPort(Protocol):
    def extract(self, *, case_id: str, parsed_artifact_ids: list[str]) -> dict[str, Any]: ...


class StartupLineageWorkflowPort(Protocol):
    def derive(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]: ...


class StartupReportWorkflowPort(Protocol):
    def build(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        readiness_snapshot_id: str,
        readiness_snapshot_hash: str,
        readiness_snapshot_revision: int,
        market_research_snapshot_id: str,
        market_research_snapshot_hash: str,
        market_research_snapshot_revision: int,
        gtm_snapshot_id: str,
        gtm_snapshot_hash: str,
        gtm_snapshot_revision: int,
        startup_claim_ids: list[str],
        evidence_fact_ids: list[str],
        calculation_ids: list[str],
        finding_ids: list[str],
        contradiction_ids: list[str],
    ) -> dict[str, str | int]: ...


class StartupProviderAnalysisResult(TypedDict, total=False):
    finding_ids: list[str]
    findings: list[Finding]


class StartupProviderWorkflowPort(Protocol):
    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> StartupProviderAnalysisResult: ...


class StartupIntelligenceBindingError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StartupReflexionWorkflowAdapter:
    trace_tool_name = "startup_reflexion"
    critic_trace_tool_name = "startup_critic"
    arbiter_trace_tool_name = "startup_arbiter"

    def __init__(
        self,
        *,
        finding_repository: Any,
        contradiction_repository: Any,
        workflow_store: Any,
        critic: StartupCriticService | None = None,
        arbiter: StartupArbiterService | None = None,
    ) -> None:
        self._finding_repository = finding_repository
        self._contradiction_repository = contradiction_repository
        self._workflow_store = workflow_store
        self._critic = critic or StartupCriticService()
        self._arbiter = arbiter or StartupArbiterService(
            contradiction_repository=contradiction_repository
        )

    def review(
        self,
        *,
        case_id: str,
        round_number: int,
        finding_ids: list[str],
        contradiction_ids: list[str],
    ) -> dict[str, object]:
        self.review_critic(
            case_id=case_id,
            round_number=round_number,
            finding_ids=finding_ids,
            contradiction_ids=contradiction_ids,
        )
        return self.arbitrate(case_id=case_id, round_number=round_number)

    def review_critic(
        self,
        *,
        case_id: str,
        round_number: int,
        finding_ids: list[str],
        contradiction_ids: list[str],
    ) -> dict[str, object]:
        try:
            case_uuid = UUID(case_id)
        except ValueError as exc:
            raise StartupIntelligenceBindingError("startup_reflexion_case_id_invalid") from exc
        selected_finding_ids = _uuid_list(
            finding_ids,
            "startup_reflexion_finding_id_invalid",
        )
        selected_contradiction_ids = _uuid_list(
            contradiction_ids,
            "startup_reflexion_contradiction_id_invalid",
        )
        findings = self._selected_findings(case_uuid, selected_finding_ids)
        contradictions = self._selected_contradictions(
            case_uuid,
            selected_contradiction_ids,
        )
        market_sources = self._market_sources(case_id, case_uuid)
        try:
            review = self._critic.review(
                case_id=case_uuid,
                round_number=round_number,
                findings=findings,
                contradictions=contradictions,
                market_sources=market_sources,
            )
        except ValueError as exc:
            raise StartupIntelligenceBindingError(str(exc)) from exc

        self._workflow_store.update(
            case_id,
            lambda _current: {
                "startup_pending_critic_review": review.model_dump(mode="json"),
            },
        )
        return {
            "critic_issue_ids": [str(issue.issue_id) for issue in review.issues],
            "critic_issue_codes": [issue.code.value for issue in review.issues],
        }

    def arbitrate(self, *, case_id: str, round_number: int) -> dict[str, object]:
        try:
            case_uuid = UUID(case_id)
        except ValueError as exc:
            raise StartupIntelligenceBindingError("startup_reflexion_case_id_invalid") from exc
        runtime = self._workflow_store.load(case_id)
        pending = runtime.get("startup_pending_critic_review")
        if not isinstance(pending, dict):
            raise StartupIntelligenceBindingError("startup_critic_review_missing")
        try:
            review = StartupCriticReview.model_validate(pending)
        except ValueError as exc:
            raise StartupIntelligenceBindingError("startup_critic_review_invalid") from exc
        if review.case_id != case_uuid or review.round_number != round_number:
            raise StartupIntelligenceBindingError("startup_critic_review_stale")
        try:
            decision = self._arbiter.decide(review)
        except ValueError as exc:
            raise StartupIntelligenceBindingError(str(exc)) from exc

        artifact = {
            "schema_version": "startup_reflexion_roles@1",
            "round_number": round_number,
            "critic": {
                "issue_count": len(review.issues),
                "issues": [
                    {
                        "issue_id": str(issue.issue_id),
                        "code": issue.code.value,
                        "severity": issue.severity.value,
                        "finding_ids": [str(item) for item in issue.finding_ids],
                        "contradiction_ids": [str(item) for item in issue.contradiction_ids],
                        "evidence_fact_ids": [str(item) for item in issue.evidence_fact_ids],
                        "source_ids": [str(item) for item in issue.source_ids],
                    }
                    for issue in review.issues
                ],
            },
            "arbiter": {
                "status": decision.status.value,
                "issue_ids": [str(item) for item in decision.issue_ids],
                "accepted_finding_ids": [
                    str(item) for item in decision.accepted_finding_ids
                ],
                "contradiction_ids": [str(item) for item in decision.contradiction_ids],
                "new_contradiction_ids": [
                    str(item) for item in decision.new_contradiction_ids
                ],
                "progress": decision.progress,
            },
        }
        def merge_history(current: dict[str, Any]) -> dict[str, Any]:
            raw_history = current.get("startup_reflexion_history", [])
            history = [
                dict(item)
                for item in raw_history
                if isinstance(raw_history, list)
                and isinstance(item, dict)
                and item.get("round_number") != round_number
            ]
            history.append(artifact)
            history.sort(key=lambda item: int(item.get("round_number", 0)))
            return {
                "startup_reflexion_artifact": artifact,
                "startup_reflexion_history": history,
                "startup_pending_critic_review": None,
            }

        self._workflow_store.update(case_id, merge_history)
        return {
            "critic_issue_ids": [str(issue.issue_id) for issue in review.issues],
            "critic_issue_codes": [issue.code.value for issue in review.issues],
            "arbiter_status": decision.status.value,
            "contradiction_ids": [str(item) for item in decision.contradiction_ids],
            "progress": decision.progress,
        }

    def _selected_findings(
        self,
        case_id: UUID,
        finding_ids: list[UUID],
    ) -> tuple[Finding, ...]:
        by_id = {
            item.id: item
            for item in self._finding_repository.list_for_case(case_id)
            if isinstance(item, Finding)
        }
        try:
            return tuple(by_id[item] for item in finding_ids)
        except KeyError as exc:
            raise StartupIntelligenceBindingError("startup_reflexion_finding_not_found") from exc

    def _selected_contradictions(
        self,
        case_id: UUID,
        contradiction_ids: list[UUID],
    ) -> tuple[Contradiction, ...]:
        by_id = {
            item.id: item
            for item in self._contradiction_repository.list_for_case(case_id)
            if isinstance(item, Contradiction)
        }
        try:
            return tuple(by_id[item] for item in contradiction_ids)
        except KeyError as exc:
            raise StartupIntelligenceBindingError(
                "startup_reflexion_contradiction_not_found"
            ) from exc

    def _market_sources(
        self,
        case_id: str,
        case_uuid: UUID,
    ) -> tuple[StartupResearchSource, ...]:
        runtime = self._workflow_store.load(case_id)
        artifact = runtime.get("startup_market_research_artifact")
        if artifact is None:
            return ()
        if not isinstance(artifact, dict):
            raise StartupIntelligenceBindingError(
                "startup_reflexion_market_snapshot_invalid"
            )
        payload = artifact.get("snapshot")
        if not isinstance(payload, dict):
            raise StartupIntelligenceBindingError(
                "startup_reflexion_market_snapshot_invalid"
            )
        try:
            snapshot = StartupMarketResearchSnapshot.model_validate(payload)
        except (TypeError, ValueError) as exc:
            raise StartupIntelligenceBindingError(
                "startup_reflexion_market_snapshot_invalid"
            ) from exc
        if snapshot.case_id != case_uuid:
            raise StartupIntelligenceBindingError(
                "startup_reflexion_market_snapshot_case_mismatch"
            )
        return snapshot.sources


class StartupDocumentIntelligenceWorkflowAdapter:
    trace_tool_name = "startup_document_intelligence"

    def __init__(self, *, workflow_store: Any) -> None:
        self._workflow_store = workflow_store
        self._service = StartupDocumentIntelligenceService()

    def analyze(
        self,
        *,
        case_id: str,
        data_revision: int,
        inventory_id: str,
        source_document_ids: list[str],
        artifact_ids: list[str],
        parsed_artifact_ids: list[str],
        evidence_fact_ids: list[str],
        startup_claim_ids: list[str],
        quarantine_reason_codes: list[str],
    ) -> dict[str, str | int]:
        try:
            snapshot = self._service.analyze(
                case_id=UUID(case_id),
                data_revision=data_revision,
                inventory_id=inventory_id,
                source_document_ids=source_document_ids,
                artifact_ids=artifact_ids,
                parsed_artifact_ids=parsed_artifact_ids,
                evidence_fact_ids=evidence_fact_ids,
                startup_claim_ids=startup_claim_ids,
                quarantine_reason_codes=quarantine_reason_codes,
            )
        except ValueError as exc:
            raise StartupIntelligenceBindingError(
                "startup_document_intelligence_input_invalid"
            ) from exc
        self._workflow_store.save(
            case_id,
            {
                "startup_document_intelligence_artifact": {
                    "schema_version": snapshot.schema_version,
                    "snapshot": snapshot.model_dump(mode="json"),
                }
            },
        )
        return {
            "document_intelligence_snapshot_id": str(snapshot.snapshot_id),
            "document_intelligence_snapshot_hash": snapshot.snapshot_hash,
            "document_intelligence_snapshot_revision": snapshot.data_revision,
        }


class StartupReadinessWorkflowAdapter:
    trace_tool_name = "startup_readiness"

    def __init__(self, *, startup_profile_repository: Any, workflow_store: Any) -> None:
        self._startup_profile_repository = startup_profile_repository
        self._workflow_store = workflow_store

    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        metric_diagnostics: list[dict[str, Any]],
        calculation_ids: list[str],
    ) -> dict[str, str | int]:
        profile = _exact_profile(
            repository=self._startup_profile_repository,
            case_id=case_id,
            profile_id=profile_id,
            profile_hash=profile_hash,
            profile_revision=profile_revision,
        )
        service = StartupReadinessService(clock=lambda: profile.built_at)
        snapshot = service.evaluate(
            profile,
            metric_diagnostics,
            calculation_ids=tuple(_uuid_list(calculation_ids, "startup_readiness_calculation_id_invalid")),
        )
        questions = service.priority_questions(snapshot)
        if questions:
            pack = StartupMetricPack.build(
                profile_id=profile.profile_id,
                profile_hash=profile.profile_hash,
                profile_revision=profile.data_revision,
                metric_ids=snapshot.metric_pack.metric_ids,
                dimensions=snapshot.metric_pack.dimensions,
                adaptive_questions=questions,
                built_at=snapshot.built_at,
            )
            snapshot = StartupReadinessSnapshot.build(
                profile_id=profile.profile_id,
                profile_hash=profile.profile_hash,
                profile_revision=profile.data_revision,
                metric_pack=pack,
                calculation_ids=snapshot.calculation_ids,
                diagnostic_ids=snapshot.diagnostic_ids,
                built_at=snapshot.built_at,
            )
        self._workflow_store.save(
            case_id,
            {
                "startup_readiness_artifact": {
                    "schema_version": snapshot.schema_version,
                    "snapshot": snapshot.model_dump(mode="json"),
                }
            },
        )
        return {
            "readiness_snapshot_id": str(snapshot.snapshot_id),
            "readiness_snapshot_hash": snapshot.snapshot_hash,
            "readiness_snapshot_revision": snapshot.profile_revision,
        }


class StartupProductValidationWorkflowAdapter:
    trace_tool_name = "startup_product_validation"

    def __init__(self, *, startup_profile_repository: Any, workflow_store: Any) -> None:
        self._startup_profile_repository = startup_profile_repository
        self._workflow_store = workflow_store
        self._service = StartupProductValidationService()

    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        evidence_fact_ids: list[str],
        startup_claim_ids: list[str],
        claim_status_by_id: dict[str, str],
        contradiction_ids: list[str],
    ) -> dict[str, str | int]:
        profile = _exact_profile(
            repository=self._startup_profile_repository,
            case_id=case_id,
            profile_id=profile_id,
            profile_hash=profile_hash,
            profile_revision=profile_revision,
        )
        snapshot = self._service.evaluate(
            profile,
            evidence_fact_ids=evidence_fact_ids,
            startup_claim_ids=startup_claim_ids,
            claim_status_by_id=claim_status_by_id,
            contradiction_ids=contradiction_ids,
        )
        artifact = {
            "schema_version": snapshot.schema_version,
            "snapshot": snapshot.model_dump(mode="json"),
        }

        def merge_history(current: dict[str, Any]) -> dict[str, Any]:
            raw_history = current.get("startup_product_validation_history", [])
            history = [
                dict(item)
                for item in raw_history
                if isinstance(raw_history, list) and isinstance(item, dict)
            ]
            history = [
                item
                for item in history
                if item.get("snapshot_id") != str(snapshot.snapshot_id)
            ]
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
            }

        self._workflow_store.update(case_id, merge_history)
        return {
            "product_validation_snapshot_id": str(snapshot.snapshot_id),
            "product_validation_snapshot_hash": snapshot.snapshot_hash,
            "product_validation_snapshot_revision": snapshot.profile_revision,
        }


class StartupGtmWorkflowAdapter:
    trace_tool_name = "startup_gtm"

    def __init__(self, *, startup_profile_repository: Any, workflow_store: Any) -> None:
        self._startup_profile_repository = startup_profile_repository
        self._workflow_store = workflow_store
        self._service = StartupGtmService()

    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        product_validation_snapshot_id: str,
        product_validation_snapshot_hash: str,
        product_validation_snapshot_revision: int,
        market_research_snapshot_id: str,
        market_research_snapshot_hash: str,
        market_research_snapshot_revision: int,
        evidence_fact_ids: list[str],
        finding_ids: list[str],
        contradiction_ids: list[str],
    ) -> dict[str, str | int]:
        profile = _exact_profile(
            repository=self._startup_profile_repository,
            case_id=case_id,
            profile_id=profile_id,
            profile_hash=profile_hash,
            profile_revision=profile_revision,
        )
        current = self._workflow_store.load(case_id)
        if not isinstance(current, dict):
            raise StartupIntelligenceBindingError("startup_gtm_runtime_missing")
        product_validation = self._product_validation_snapshot(
            current,
            snapshot_id=product_validation_snapshot_id,
            snapshot_hash=product_validation_snapshot_hash,
            snapshot_revision=product_validation_snapshot_revision,
        )
        market_research = self._market_research_snapshot(
            current,
            snapshot_id=market_research_snapshot_id,
            snapshot_hash=market_research_snapshot_hash,
            snapshot_revision=market_research_snapshot_revision,
        )
        snapshot = self._service.evaluate(
            profile,
            product_validation=product_validation,
            market_research=market_research,
            evidence_fact_ids=evidence_fact_ids,
            finding_ids=finding_ids,
            contradiction_ids=contradiction_ids,
        )
        artifact = {
            "schema_version": snapshot.schema_version,
            "snapshot": snapshot.model_dump(mode="json"),
        }

        def merge_history(runtime: dict[str, Any]) -> dict[str, Any]:
            raw_history = runtime.get("startup_gtm_history", [])
            history = [
                dict(item)
                for item in raw_history
                if isinstance(raw_history, list) and isinstance(item, dict)
            ]
            history = [
                item
                for item in history
                if item.get("snapshot_id") != str(snapshot.snapshot_id)
            ]
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
            }

        self._workflow_store.update(case_id, merge_history)
        return {
            "gtm_snapshot_id": str(snapshot.snapshot_id),
            "gtm_snapshot_hash": snapshot.snapshot_hash,
            "gtm_snapshot_revision": snapshot.data_revision,
        }

    @staticmethod
    def _product_validation_snapshot(
        runtime: dict[str, Any],
        *,
        snapshot_id: str,
        snapshot_hash: str,
        snapshot_revision: int,
    ) -> StartupProductValidationSnapshot:
        raw_artifact = runtime.get("startup_product_validation_artifact")
        if not isinstance(raw_artifact, dict):
            raise StartupIntelligenceBindingError(
                "startup_gtm_product_validation_snapshot_invalid"
            )
        try:
            raw_snapshot = raw_artifact["snapshot"]
            snapshot = StartupProductValidationSnapshot.model_validate(raw_snapshot)
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupIntelligenceBindingError(
                "startup_gtm_product_validation_snapshot_invalid"
            ) from exc
        if (
            str(snapshot.snapshot_id) != snapshot_id
            or snapshot.snapshot_hash != snapshot_hash
            or snapshot.profile_revision != snapshot_revision
        ):
            raise StartupIntelligenceBindingError(
                "startup_gtm_product_validation_snapshot_mismatch"
            )
        return snapshot

    @staticmethod
    def _market_research_snapshot(
        runtime: dict[str, Any],
        *,
        snapshot_id: str,
        snapshot_hash: str,
        snapshot_revision: int,
    ) -> StartupMarketResearchSnapshot:
        raw_artifact = runtime.get("startup_market_research_artifact")
        if not isinstance(raw_artifact, dict):
            raise StartupIntelligenceBindingError(
                "startup_gtm_market_research_snapshot_invalid"
            )
        try:
            raw_snapshot = raw_artifact["snapshot"]
            snapshot = StartupMarketResearchSnapshot.model_validate(raw_snapshot)
        except (KeyError, TypeError, ValueError) as exc:
            raise StartupIntelligenceBindingError(
                "startup_gtm_market_research_snapshot_invalid"
            ) from exc
        if (
            str(snapshot.snapshot_id) != snapshot_id
            or snapshot.snapshot_hash != snapshot_hash
            or snapshot.data_revision != snapshot_revision
        ):
            raise StartupIntelligenceBindingError(
                "startup_gtm_market_research_snapshot_mismatch"
            )
        return snapshot


class StartupGtmQueryRepositoryAdapter:
    def __init__(self, *, workflow_store: Any) -> None:
        self._workflow_store = workflow_store

    def get_current(self, case_id: str) -> StartupGtmSnapshot:
        runtime = self._workflow_store.load(case_id)
        if not isinstance(runtime, dict):
            raise KeyError(f"startup_gtm_not_found:{case_id}")
        artifact = runtime.get("startup_gtm_artifact")
        if not isinstance(artifact, dict):
            raise KeyError(f"startup_gtm_not_found:{case_id}")
        try:
            snapshot = StartupGtmSnapshot.model_validate(artifact["snapshot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("startup_gtm_artifact_invalid") from exc
        if artifact.get("schema_version") != snapshot.schema_version:
            raise ValueError("startup_gtm_artifact_invalid")
        if (
            runtime.get("gtm_snapshot_id") != str(snapshot.snapshot_id)
            or runtime.get("gtm_snapshot_hash") != snapshot.snapshot_hash
            or runtime.get("gtm_snapshot_revision") != snapshot.data_revision
            or runtime.get("profile_id") != str(snapshot.profile_id)
            or runtime.get("product_validation_snapshot_id")
            != str(snapshot.product_validation_snapshot_id)
            or runtime.get("market_research_snapshot_id")
            != str(snapshot.market_research_snapshot_id)
            or runtime.get("data_revision") != snapshot.data_revision
        ):
            raise ValueError("startup_gtm_artifact_stale")
        return snapshot


class StartupMarketResearchWorkflowAdapter:
    trace_tool_name = "startup_market_research"

    def __init__(
        self,
        *,
        startup_profile_repository: Any,
        workflow_store: Any,
        research_port: StartupResearchPort,
    ) -> None:
        self._startup_profile_repository = startup_profile_repository
        self._workflow_store = workflow_store
        self._research_port = research_port

    def research(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
    ) -> dict[str, str | int]:
        profile = _exact_profile(
            repository=self._startup_profile_repository,
            case_id=case_id,
            profile_id=profile_id,
            profile_hash=profile_hash,
            profile_revision=profile_revision,
        )
        cached_live = self._current_live_snapshot(case_id=case_id, profile=profile)
        if cached_live is not None:
            return {
                "market_research_snapshot_id": str(cached_live.snapshot_id),
                "market_research_snapshot_hash": cached_live.snapshot_hash,
                "market_research_snapshot_revision": cached_live.data_revision,
            }
        plan_result = StartupMarketResearchService(
            clock=lambda: profile.built_at
        ).build_research_plan(profile)
        collected = self._research_port.collect(plan_result.plan)
        if collected.case_id != profile.case_id:
            raise StartupIntelligenceBindingError("startup_market_research_case_mismatch")
        if collected.source_mode is not StartupResearchSourceMode.FROZEN:
            raise StartupIntelligenceBindingError("startup_market_research_frozen_required")
        snapshot = StartupMarketResearchSnapshot.build(
            case_id=collected.case_id,
            as_of=collected.as_of,
            source_mode=collected.source_mode,
            research_id=collected.research_id,
            competitors=collected.competitors,
            sources=collected.sources,
            sentiment_signals=collected.sentiment_signals,
            assumptions=collected.assumptions,
            sizing=collected.sizing,
            labels=tuple((*collected.labels, *plan_result.gap_codes)),
            data_revision=profile.data_revision,
        )
        self._workflow_store.save(
            case_id,
            {
                "startup_market_research_artifact": {
                    "schema_version": snapshot.schema_version,
                    "snapshot": snapshot.model_dump(mode="json"),
                    "plan": plan_result.plan.model_dump(mode="json"),
                    "gap_codes": list(plan_result.gap_codes),
                    "omitted_values": list(plan_result.omitted_values),
                }
            },
        )
        return {
            "market_research_snapshot_id": str(snapshot.snapshot_id),
            "market_research_snapshot_hash": snapshot.snapshot_hash,
            "market_research_snapshot_revision": snapshot.data_revision,
        }

    def _current_live_snapshot(
        self,
        *,
        case_id: str,
        profile: StartupProfile,
    ) -> StartupMarketResearchSnapshot | None:
        runtime = self._workflow_store.load(case_id)
        if not isinstance(runtime, dict):
            raise StartupIntelligenceBindingError(
                "startup_market_research_runtime_invalid"
            )
        artifact = runtime.get("startup_market_research_artifact")
        if not isinstance(artifact, dict):
            return None
        raw_snapshot = artifact.get("snapshot")
        if not isinstance(raw_snapshot, dict):
            return None
        if raw_snapshot.get("source_mode") != StartupResearchSourceMode.LIVE.value:
            return None
        try:
            snapshot = StartupMarketResearchSnapshot.model_validate(raw_snapshot)
        except (TypeError, ValueError) as exc:
            raise StartupIntelligenceBindingError(
                "startup_market_research_live_snapshot_invalid"
            ) from exc
        if artifact.get("schema_version") != snapshot.schema_version:
            raise StartupIntelligenceBindingError(
                "startup_market_research_live_snapshot_invalid"
            )
        if snapshot.case_id != profile.case_id:
            raise StartupIntelligenceBindingError(
                "startup_market_research_live_snapshot_case_mismatch"
            )
        if snapshot.data_revision != profile.data_revision:
            raise StartupIntelligenceBindingError(
                "startup_market_research_live_snapshot_revision_mismatch"
            )
        if (
            runtime.get("market_research_snapshot_id") != str(snapshot.snapshot_id)
            or runtime.get("market_research_snapshot_hash") != snapshot.snapshot_hash
            or runtime.get("market_research_snapshot_revision") != snapshot.data_revision
        ):
            raise StartupIntelligenceBindingError(
                "startup_market_research_live_snapshot_marker_mismatch"
            )
        return snapshot


class StartupClaimRepositoryAdapter:
    def __init__(
        self,
        claim_repository: Any,
        *,
        evidence_repository: Any | None = None,
        calculation_repository: Any | None = None,
        contradiction_repository: Any | None = None,
    ) -> None:
        self._claim_repository = claim_repository
        self._evidence_repository = evidence_repository
        self._calculation_repository = calculation_repository
        self._contradiction_repository = contradiction_repository

    def extract(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        case_uuid = UUID(case_id)
        claims = self._claim_repository.list_for_case(case_uuid)
        if self._evidence_repository is None or self._calculation_repository is None:
            return {"startup_claim_ids": [str(getattr(claim, "id")) for claim in claims]}
        selected_fact_ids = {UUID(item) for item in evidence_fact_ids}
        facts = [
            fact
            for fact in self._evidence_repository.list_for_case(case_uuid)
            if getattr(fact, "id") in selected_fact_ids
            and "startup_claim_id" not in getattr(fact, "metadata", {})
        ]
        calculations = self._calculation_repository.list_for_case(case_uuid)
        matrix = ClaimEvidenceService(
            contradiction_repository=self._contradiction_repository,
        ).build(
            case_id=case_uuid,
            claims=claims,
            evidence_facts=facts,
            calculations=calculations,
        )
        contradiction_ids = [
            str(contradiction_id)
            for row in matrix.rows
            for contradiction_id in row.contradiction_ids
        ]
        return {
            "startup_claim_ids": [str(row.claim.id) for row in matrix.rows],
            "contradiction_ids": list(dict.fromkeys(contradiction_ids)),
            "claim_status_by_id": {
                str(row.claim.id): row.status.value for row in matrix.rows
            },
            "claim_matrix_summary": [
                {
                    "claim_id": str(row.claim.id),
                    "status": row.status.value,
                    "link_count": len(row.links),
                    "contradiction_ids": [str(item) for item in row.contradiction_ids],
                    "executive_summary_eligible": row.executive_summary_eligible,
                }
                for row in matrix.rows
            ],
        }


class StartupEvidenceRepositoryAdapter:
    def __init__(self, evidence_repository: Any) -> None:
        self._evidence_repository = evidence_repository

    def extract(self, *, case_id: str, parsed_artifact_ids: list[str]) -> dict[str, Any]:
        facts = self._evidence_repository.list_for_case(UUID(case_id))
        fact_ids = [str(getattr(fact, "id")) for fact in facts]
        return {
            "evidence_fact_ids": fact_ids,
        }

class StartupLineageRepositoryAdapter:
    def __init__(self, review_repository: Any) -> None:
        self._review_repository = review_repository

    def derive(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        root_fact_ids = {UUID(item) for item in evidence_fact_ids}
        if not root_fact_ids:
            return {
                "dependency_edges": {},
                "dependency_node_edges": {},
            }
        case_uuid = UUID(case_id)
        calculations = self._review_repository.list_calculations_for_facts(root_fact_ids)
        calculation_ids = {item.id for item in calculations}
        findings = self._review_repository.list_findings_for_dependencies(root_fact_ids, calculation_ids)
        finding_ids = {item.id for item in findings}
        contradictions = self._review_repository.list_contradictions_for_dependencies(
            root_fact_ids, finding_ids
        )
        reports = self._review_repository.list_report_snapshots_for_case(case_uuid)
        latest_report_id = str(reports[-1].id) if reports else None

        dependency_edges: dict[str, list[str]] = {str(item): [] for item in root_fact_ids}
        dependency_node_edges: dict[str, list[str]] = {
            str(item): ["product_validation", "metrics", "gtm"]
            for item in root_fact_ids
        }
        for calculation in calculations:
            calculation_id = str(calculation.id)
            for fact_id in calculation.input_fact_ids:
                if fact_id in root_fact_ids:
                    _append_unique(dependency_edges.setdefault(str(fact_id), []), calculation_id)
            dependency_node_edges[calculation_id] = ["financial_analysis", "risk_analysis"]
        for finding in findings:
            finding_id = str(finding.id)
            for fact_id in (*finding.evidence_fact_ids, *finding.counter_evidence_fact_ids):
                if fact_id in root_fact_ids:
                    _append_unique(dependency_edges.setdefault(str(fact_id), []), finding_id)
            for calculation_id in finding.calculation_ids:
                if calculation_id in calculation_ids:
                    _append_unique(dependency_edges.setdefault(str(calculation_id), []), finding_id)
            dependency_node_edges[finding_id] = ["gtm", "critic", "arbiter"]
        for contradiction in contradictions:
            contradiction_id = str(contradiction.id)
            for fact_id in contradiction.fact_ids:
                if fact_id in root_fact_ids:
                    _append_unique(dependency_edges.setdefault(str(fact_id), []), contradiction_id)
            for finding_id in contradiction.finding_ids:
                if finding_id in finding_ids:
                    _append_unique(dependency_edges.setdefault(str(finding_id), []), contradiction_id)
            dependency_node_edges[contradiction_id] = ["gtm", "report"]
        if latest_report_id is not None:
            for fact_id in root_fact_ids:
                _append_unique(dependency_edges.setdefault(str(fact_id), []), latest_report_id)
            for calculation_id in calculation_ids:
                _append_unique(dependency_edges.setdefault(str(calculation_id), []), latest_report_id)
            for finding_id in finding_ids:
                _append_unique(dependency_edges.setdefault(str(finding_id), []), latest_report_id)
            for contradiction in contradictions:
                _append_unique(dependency_edges.setdefault(str(contradiction.id), []), latest_report_id)
        return {
            "dependency_edges": dependency_edges,
            "dependency_node_edges": dependency_node_edges,
        }


class StartupReportTraceLineageError(RuntimeError):
    retryable = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StartupReportRepositoryAdapter:
    def __init__(
        self,
        *,
        case_repository: Any,
        startup_claim_repository: Any,
        startup_profile_repository: Any,
        evidence_repository: Any,
        calculation_repository: Any,
        finding_repository: Any,
        contradiction_repository: Any,
        report_repository: Any,
        approval_repository: Any,
        current_data_revision: Callable[[UUID], int],
        report_service: ReportService,
        output_dir: Path,
        audit_spool: AuditSpool,
        workflow_store: Any | None = None,
        builder: StartupReportSnapshotBuilder | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._case_repository = case_repository
        self._startup_claim_repository = startup_claim_repository
        self._startup_profile_repository = startup_profile_repository
        self._evidence_repository = evidence_repository
        self._calculation_repository = calculation_repository
        self._finding_repository = finding_repository
        self._contradiction_repository = contradiction_repository
        self._report_repository = report_repository
        self._freeze_service = StartupReportFreezeService(
            approval_repository,
            current_data_revision=current_data_revision,
            clock=clock,
        )
        self._approval_repository = approval_repository
        self._current_data_revision = current_data_revision
        self._report_service = report_service
        self._output_dir = output_dir
        self._audit_spool = audit_spool
        self._workflow_store = workflow_store
        self._builder = builder or StartupReportSnapshotBuilder()

    def build(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        startup_claim_ids: list[str],
        evidence_fact_ids: list[str],
        calculation_ids: list[str],
        finding_ids: list[str],
        contradiction_ids: list[str],
        readiness_snapshot_id: str | None = None,
        readiness_snapshot_hash: str | None = None,
        readiness_snapshot_revision: int | None = None,
        market_research_snapshot_id: str | None = None,
        market_research_snapshot_hash: str | None = None,
        market_research_snapshot_revision: int | None = None,
        gtm_snapshot_id: str | None = None,
        gtm_snapshot_hash: str | None = None,
        gtm_snapshot_revision: int | None = None,
    ) -> dict[str, str | int]:
        case_uuid = UUID(case_id)
        case = self._case_repository.get(case_uuid)
        profile = self._exact_current_profile(
            case=case,
            profile_id=profile_id,
            profile_hash=profile_hash,
            profile_revision=profile_revision,
        )
        facts = _select_by_id(
            self._evidence_repository.list_for_case(case_uuid),
            evidence_fact_ids,
        )
        readiness = self._exact_readiness_snapshot(
            case_id=case_id,
            profile=profile,
            snapshot_id=readiness_snapshot_id,
            snapshot_hash=readiness_snapshot_hash,
            snapshot_revision=readiness_snapshot_revision,
        )
        market_research = self._exact_market_research_snapshot(
            case_id=case_id,
            case=case,
            snapshot_id=market_research_snapshot_id,
            snapshot_hash=market_research_snapshot_hash,
            snapshot_revision=market_research_snapshot_revision,
        )
        gtm = self._exact_gtm_snapshot(
            case_id=case_id,
            case=case,
            profile=profile,
            market_research=market_research,
            snapshot_id=gtm_snapshot_id,
            snapshot_hash=gtm_snapshot_hash,
            snapshot_revision=gtm_snapshot_revision,
        )
        source_hashes = _source_hashes(facts)
        if market_research is not None:
            source_hashes.update(
                {
                    f"market-source-{source.source_id}": source.source_hash
                    for source in market_research.sources
                }
            )
        report_input = _StartupRepositoryReportInput(
            case=case,
            startup_profile=profile,
            startup_claims=_select_by_id(
                self._startup_claim_repository.list_for_case(case_uuid),
                startup_claim_ids,
            ),
            facts=facts,
            calculations=_select_by_id(
                self._calculation_repository.list_for_case(case_uuid),
                calculation_ids,
            ),
            findings=_select_by_id(
                self._finding_repository.list_for_case(case_uuid),
                finding_ids,
            ),
            contradictions=_select_by_id(
                self._contradiction_repository.list_for_case(case_uuid),
                contradiction_ids,
            ),
            source_hashes=source_hashes,
            trace_ids=self._trace_ids_for_latest_run(case_id),
            startup_readiness=readiness,
            startup_market_research=market_research,
            startup_gtm=gtm,
        )
        draft = self._report_service.render_draft(
            self._builder.build(report_input),
            self._output_dir,
        )
        return {
            "report_snapshot_id": str(draft.snapshot.id),
            "report_snapshot_hash": draft.snapshot.report_hash,
            "report_snapshot_revision": draft.snapshot.data_revision,
        }

    def _trace_ids_for_latest_run(self, case_id: str) -> tuple[str, ...]:
        try:
            events = self._audit_spool.read_batch(limit=_REPORT_TRACE_READ_LIMIT)
        except Exception as exc:
            raise StartupReportTraceLineageError(
                "startup_report_trace_lineage_unavailable"
            ) from exc
        if len(events) >= _REPORT_TRACE_READ_LIMIT:
            raise StartupReportTraceLineageError("startup_report_trace_lineage_truncated")
        indexed_events = [
            (index, event)
            for index, event in enumerate(events)
            if _is_correlatable_startup_node_event(event, case_id=case_id)
        ]
        if not indexed_events:
            raise StartupReportTraceLineageError("startup_report_trace_lineage_missing")
        latest_run_id = max(
            indexed_events,
            key=lambda item: (item[1].timestamp_utc, item[0]),
        )[1].run_id
        selected = sorted(
            (
                item
                for item in indexed_events
                if item[1].run_id == latest_run_id
                and item[1].attributes.get("node_name") != "report"
            ),
            key=lambda item: (item[1].timestamp_utc, item[0]),
        )
        trace_ids = sorted(
            {
                cast(str, event.attributes["checkpoint_id"])
                for _, event in selected
            }
        )
        if not trace_ids:
            raise StartupReportTraceLineageError("startup_report_trace_lineage_missing")
        return tuple(trace_ids)

    def _exact_current_profile(
        self,
        *,
        case: DueDiligenceCase,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
    ) -> StartupProfile:
        try:
            profile_uuid = UUID(profile_id)
        except ValueError as exc:
            raise StartupReportProfileBindingError(
                "startup_report_profile_reference_invalid"
            ) from exc
        try:
            profile = cast(StartupProfile, self._startup_profile_repository.get(profile_uuid))
        except KeyError as exc:
            raise StartupReportProfileBindingError("startup_report_profile_not_found") from exc
        if profile.case_id != case.case_id:
            raise StartupReportProfileBindingError("cross_case_startup_profile_input")
        if profile.profile_hash != profile_hash:
            raise StartupReportProfileBindingError("startup_report_profile_hash_mismatch")
        if profile.data_revision != profile_revision:
            raise StartupReportProfileBindingError("startup_report_profile_revision_mismatch")
        if profile.data_revision != case.data_revision:
            raise StartupReportProfileBindingError("startup_report_profile_stale")
        try:
            current = cast(
                StartupProfile,
                self._startup_profile_repository.get_current(case.case_id),
            )
        except KeyError as exc:
            raise StartupReportProfileBindingError("startup_report_profile_not_found") from exc
        if (
            current.profile_id != profile.profile_id
            or current.profile_hash != profile.profile_hash
            or current.data_revision != profile.data_revision
        ):
            raise StartupReportProfileBindingError("startup_report_profile_not_current")
        return profile

    def _exact_readiness_snapshot(
        self,
        *,
        case_id: str,
        profile: StartupProfile,
        snapshot_id: str | None,
        snapshot_hash: str | None,
        snapshot_revision: int | None,
    ) -> StartupReadinessSnapshot | None:
        identity = (snapshot_id, snapshot_hash, snapshot_revision)
        if identity == (None, None, None):
            return None
        if any(value is None for value in identity):
            raise StartupReportProfileBindingError("startup_report_readiness_identity_incomplete")
        artifact = self._runtime_artifact(case_id, "startup_readiness_artifact")
        snapshot = _model_from_artifact(
            artifact,
            StartupReadinessSnapshot,
            "startup_report_readiness_artifact_invalid",
        )
        if str(snapshot.snapshot_id) != snapshot_id:
            raise StartupReportProfileBindingError("startup_report_readiness_id_mismatch")
        if snapshot.snapshot_hash != snapshot_hash:
            raise StartupReportProfileBindingError("startup_report_readiness_hash_mismatch")
        if snapshot.profile_revision != snapshot_revision:
            raise StartupReportProfileBindingError("startup_report_readiness_revision_mismatch")
        if (
            snapshot.profile_id != profile.profile_id
            or snapshot.profile_hash != profile.profile_hash
            or snapshot.profile_revision != profile.data_revision
        ):
            raise StartupReportProfileBindingError("startup_report_readiness_profile_mismatch")
        return snapshot

    def _exact_market_research_snapshot(
        self,
        *,
        case_id: str,
        case: DueDiligenceCase,
        snapshot_id: str | None,
        snapshot_hash: str | None,
        snapshot_revision: int | None,
    ) -> StartupMarketResearchSnapshot | None:
        identity = (snapshot_id, snapshot_hash, snapshot_revision)
        if identity == (None, None, None):
            return None
        if any(value is None for value in identity):
            raise StartupReportProfileBindingError(
                "startup_report_market_research_identity_incomplete"
            )
        artifact = self._runtime_artifact(case_id, "startup_market_research_artifact")
        snapshot = _model_from_artifact(
            artifact,
            StartupMarketResearchSnapshot,
            "startup_report_market_research_artifact_invalid",
        )
        if str(snapshot.snapshot_id) != snapshot_id:
            raise StartupReportProfileBindingError("startup_report_market_research_id_mismatch")
        if snapshot.snapshot_hash != snapshot_hash:
            raise StartupReportProfileBindingError("startup_report_market_research_hash_mismatch")
        if snapshot.data_revision != snapshot_revision:
            raise StartupReportProfileBindingError(
                "startup_report_market_research_revision_mismatch"
            )
        if snapshot.case_id != case.case_id:
            raise StartupReportProfileBindingError("startup_report_market_research_case_mismatch")
        if snapshot.data_revision != case.data_revision:
            raise StartupReportProfileBindingError("startup_report_market_research_stale")
        return snapshot

    def _exact_gtm_snapshot(
        self,
        *,
        case_id: str,
        case: DueDiligenceCase,
        profile: StartupProfile,
        market_research: StartupMarketResearchSnapshot | None,
        snapshot_id: str | None,
        snapshot_hash: str | None,
        snapshot_revision: int | None,
    ) -> StartupGtmSnapshot | None:
        identity = (snapshot_id, snapshot_hash, snapshot_revision)
        if identity == (None, None, None):
            return None
        if any(value is None for value in identity):
            raise StartupReportProfileBindingError(
                "startup_report_gtm_identity_incomplete"
            )
        artifact = self._runtime_artifact(case_id, "startup_gtm_artifact")
        snapshot = _model_from_artifact(
            artifact,
            StartupGtmSnapshot,
            "startup_report_gtm_artifact_invalid",
        )
        if str(snapshot.snapshot_id) != snapshot_id:
            raise StartupReportProfileBindingError("startup_report_gtm_id_mismatch")
        if snapshot.snapshot_hash != snapshot_hash:
            raise StartupReportProfileBindingError("startup_report_gtm_hash_mismatch")
        if snapshot.data_revision != snapshot_revision:
            raise StartupReportProfileBindingError("startup_report_gtm_revision_mismatch")
        if snapshot.case_id != case.case_id:
            raise StartupReportProfileBindingError("startup_report_gtm_case_mismatch")
        if snapshot.data_revision != case.data_revision:
            raise StartupReportProfileBindingError("startup_report_gtm_stale")
        if snapshot.profile_id != profile.profile_id:
            raise StartupReportProfileBindingError("startup_report_gtm_profile_mismatch")
        if (
            market_research is None
            or snapshot.market_research_snapshot_id != market_research.snapshot_id
        ):
            raise StartupReportProfileBindingError(
                "startup_report_gtm_market_research_mismatch"
            )
        product_artifact = self._runtime_artifact(
            case_id,
            "startup_product_validation_artifact",
        )
        product_validation = _model_from_artifact(
            product_artifact,
            StartupProductValidationSnapshot,
            "startup_report_gtm_product_validation_artifact_invalid",
        )
        if snapshot.product_validation_snapshot_id != product_validation.snapshot_id:
            raise StartupReportProfileBindingError(
                "startup_report_gtm_product_validation_mismatch"
            )
        if (
            product_validation.case_id != case.case_id
            or product_validation.profile_id != profile.profile_id
            or product_validation.profile_hash != profile.profile_hash
            or product_validation.profile_revision != profile.data_revision
        ):
            raise StartupReportProfileBindingError(
                "startup_report_gtm_product_validation_stale"
            )
        return snapshot

    def _runtime_artifact(self, case_id: str, key: str) -> dict[str, Any]:
        if self._workflow_store is None:
            raise StartupReportProfileBindingError("startup_report_intelligence_store_missing")
        runtime = self._workflow_store.load(case_id)
        artifact = runtime.get(key)
        if not isinstance(artifact, dict):
            raise StartupReportProfileBindingError(f"{key}_missing")
        return artifact

    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot:
        return _canonical_tuple(self._current_snapshot(case_id))

    def canonical_json_bytes(self, case_id: str) -> bytes:
        return startup_canonical_snapshot_json(self._current_snapshot(case_id))

    def founder_json_bytes(self, case_id: str) -> bytes:
        founder_view = FounderStartupReportPresentationService().build(
            self._current_snapshot(case_id)
        )
        return founder_view.model_dump_json().encode("utf-8")

    def html(self, case_id: str) -> str:
        snapshot = self._current_snapshot(case_id)
        path = self._html_path(snapshot)
        if not path.exists():
            snapshot = self._render_current(snapshot)
            path = self._html_path(snapshot)
        return path.read_text(encoding="utf-8")

    def pdf(self, case_id: str) -> bytes:
        snapshot = self._current_snapshot(case_id)
        try:
            result = self._report_service.render_final_pdf(snapshot, self._output_dir)
        except ReportFreezeRequired as exc:
            raise RuntimeError("gate_4_freeze_required") from exc
        except ReportRendererUnavailable as exc:
            raise RuntimeError("report_renderer_unavailable") from exc
        return result.pdf_path.read_bytes()

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: str,
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        snapshot = self._gate4_decision_snapshot(case_id)
        latest = self._freeze_service.latest_exact_decision(snapshot)
        if (
            latest is not None
            and latest.action == decision
            and latest.comment == reason
        ):
            return _canonical_tuple(snapshot)
        self._freeze_service.decide(
            snapshot,
            action=decision,
            snapshot_hash=snapshot_hash,
            snapshot_revision=snapshot_revision,
            comment=reason,
        )
        return _canonical_tuple(snapshot)

    def freeze_status(self, case_id: str) -> FreezeStatus:
        try:
            snapshot = self._current_snapshot(case_id)
        except KeyError:
            return "required"
        if self._current_data_revision(snapshot.case_id) != snapshot.data_revision:
            return "required"
        approvals = [
            approval
            for approval in self._approval_repository.list_for_case(snapshot.case_id)
            if approval.gate == "gate_4"
            and approval.subject_id == snapshot.id
            and approval.subject_hash == snapshot.report_hash
            and approval.subject_version == snapshot.version
            and approval.data_revision == snapshot.data_revision
        ]
        if not approvals:
            return "required"
        latest = max(approvals, key=lambda approval: (approval.decided_at, str(approval.id)))
        return "approved" if latest.action == "approved" else "required"

    def pdf_status(self, case_id: str) -> PdfStatus:
        return "ready" if self.freeze_status(case_id) == "approved" else "freeze_required"

    def _current_snapshot(self, case_id: str) -> ReportSnapshot:
        case_uuid = UUID(case_id)
        current_revision = self._current_data_revision(case_uuid)
        bound_snapshot = self._runtime_bound_current_snapshot(
            case_id,
            case_uuid=case_uuid,
            current_revision=current_revision,
        )
        if bound_snapshot is not None:
            return _ordered_startup_snapshot(bound_snapshot)
        snapshots = [
            snapshot
            for snapshot in self._startup_snapshots(case_uuid)
            if snapshot.data_revision == current_revision
        ]
        if not snapshots:
            raise KeyError(f"report_snapshot_not_found:{case_id}")
        return _ordered_startup_snapshot(snapshots[-1])

    def _gate4_decision_snapshot(self, case_id: str) -> ReportSnapshot:
        case_uuid = UUID(case_id)
        current_revision = self._current_data_revision(case_uuid)
        bound_snapshot = self._runtime_bound_current_snapshot(
            case_id,
            case_uuid=case_uuid,
            current_revision=current_revision,
        )
        if bound_snapshot is not None:
            return _ordered_startup_snapshot(bound_snapshot)
        return self._latest_startup_snapshot(case_id)

    def _runtime_bound_current_snapshot(
        self,
        case_id: str,
        *,
        case_uuid: UUID,
        current_revision: int,
    ) -> ReportSnapshot | None:
        if self._workflow_store is None:
            return None
        runtime = self._workflow_store.load(case_id)
        if not isinstance(runtime, dict):
            raise StartupReportProfileBindingError("startup_report_runtime_invalid")
        snapshot_id = runtime.get("canonical_report_snapshot_id")
        snapshot_hash = runtime.get("canonical_report_snapshot_hash")
        snapshot_revision = runtime.get("canonical_report_snapshot_revision")
        identity = (snapshot_id, snapshot_hash, snapshot_revision)
        if identity == (None, None, None):
            return None
        if any(value is None for value in identity):
            raise StartupReportProfileBindingError(
                "startup_report_canonical_identity_incomplete"
            )
        try:
            selected_id = UUID(str(snapshot_id))
        except ValueError as exc:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_id_invalid"
            ) from exc
        if not isinstance(snapshot_hash, str) or not snapshot_hash:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_hash_invalid"
            )
        if not isinstance(snapshot_revision, int):
            raise StartupReportProfileBindingError(
                "startup_report_canonical_revision_invalid"
            )
        if snapshot_revision != current_revision:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_revision_mismatch"
            )
        snapshots = self._startup_snapshots(case_uuid)
        selected = next((snapshot for snapshot in snapshots if snapshot.id == selected_id), None)
        if selected is None:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_snapshot_not_found"
            )
        if selected.case_id != case_uuid:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_case_mismatch"
            )
        if selected.report_hash != snapshot_hash:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_hash_mismatch"
            )
        if selected.data_revision != snapshot_revision:
            raise StartupReportProfileBindingError(
                "startup_report_canonical_snapshot_revision_mismatch"
            )
        return selected

    def _latest_startup_snapshot(self, case_id: str) -> ReportSnapshot:
        case_uuid = UUID(case_id)
        snapshots = self._startup_snapshots(case_uuid)
        if not snapshots:
            raise KeyError(f"report_snapshot_not_found:{case_id}")
        return _ordered_startup_snapshot(snapshots[-1])

    def _render_current(self, snapshot: ReportSnapshot) -> ReportSnapshot:
        if is_startup_report_snapshot(snapshot):
            self._output_dir.mkdir(parents=True, exist_ok=True)
            self._html_path(snapshot).write_text(
                self._report_service.render_html(snapshot),
                encoding="utf-8",
            )
            return snapshot
        return self._report_service.render_draft(snapshot, self._output_dir).snapshot

    def _startup_snapshots(self, case_id: UUID) -> list[ReportSnapshot]:
        snapshots = [
            snapshot
            for snapshot in cast(
                list[ReportSnapshot],
                self._report_repository.list_for_case(case_id),
            )
            if is_startup_report_snapshot(snapshot)
        ]
        return sorted(
            snapshots,
            key=lambda snapshot: (
                snapshot.data_revision,
                snapshot.created_at,
                str(snapshot.id),
            ),
        )

    def _html_path(self, snapshot: ReportSnapshot) -> Path:
        return self._output_dir / f"{snapshot.id}.report.html"


@dataclass(frozen=True)
class _StartupRepositoryReportInput:
    case: DueDiligenceCase
    startup_profile: StartupProfile
    startup_claims: tuple[StartupClaim, ...]
    facts: tuple[EvidenceFact, ...]
    calculations: tuple[Calculation, ...]
    findings: tuple[Finding, ...]
    contradictions: tuple[Contradiction, ...]
    source_hashes: dict[str, str]
    trace_ids: tuple[str, ...]
    startup_readiness: StartupReadinessSnapshot | None = None
    startup_market_research: StartupMarketResearchSnapshot | None = None
    startup_gtm: StartupGtmSnapshot | None = None


def _is_correlatable_startup_node_event(event: AuditEvent, *, case_id: str) -> bool:
    attributes = event.attributes
    checkpoint_id = attributes.get("checkpoint_id")
    checkpoint_hash = attributes.get("checkpoint_hash")
    node_name = attributes.get("node_name")
    return (
        event.schema_version == "audit_event@1"
        and event.event_type == "span"
        and event.span_name == "analysis.module"
        and attributes.get("schema_version") == "startup_node_audit@1"
        and attributes.get("case_id") == case_id
        and isinstance(node_name, str)
        and bool(node_name)
        and isinstance(checkpoint_id, str)
        and _STARTUP_CHECKPOINT_ID_RE.fullmatch(checkpoint_id) is not None
        and isinstance(checkpoint_hash, str)
        and _SHA256_HEX_RE.fullmatch(checkpoint_hash) is not None
    )


class StartupMetricWorkflowAdapter:
    trace_tool_name = "python_metrics"

    def __init__(
        self,
        service: StartupMetricService,
        *,
        metric_names: tuple[str, ...] = ("gross_margin",),
        evidence_repository: Any | None = None,
    ) -> None:
        self._service = service
        self._metric_names = metric_names
        self._evidence_repository = evidence_repository

    def calculate(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        calculation_ids: list[str] = []
        case_uuid = UUID(case_id)
        fact_ids = [UUID(item) for item in evidence_fact_ids]
        facts_by_id = self._facts_by_id(case_uuid, fact_ids)
        metric_diagnostics: list[dict[str, Any]] = []
        for metric_name in self._metric_names:
            relevant_fact_ids = _relevant_startup_metric_fact_ids(metric_name, facts_by_id)
            result = self._service.calculate_for_case(
                case_uuid,
                metric_name,
                evidence_fact_ids=relevant_fact_ids,
            )
            calculation_id = getattr(result, "calculation_id", None)
            if calculation_id is not None:
                calculation_ids.append(str(calculation_id))
            metric_diagnostics.append(_metric_diagnostic(metric_name, result, relevant_fact_ids))
        return {"calculation_ids": calculation_ids, "metric_diagnostics": metric_diagnostics}

    def _facts_by_id(
        self,
        case_id: UUID,
        evidence_fact_ids: list[UUID],
    ) -> dict[UUID, Any]:
        if self._evidence_repository is None:
            return {fact_id: None for fact_id in evidence_fact_ids}
        selected = set(evidence_fact_ids)
        return {
            fact.id: fact
            for fact in self._evidence_repository.list_for_case(case_id)
            if fact.id in selected
        }


def _relevant_startup_metric_fact_ids(metric_name: str, facts_by_id: dict[UUID, Any]) -> list[UUID]:
    if not facts_by_id or any(fact is None for fact in facts_by_id.values()):
        return list(facts_by_id)
    definition = STARTUP_METRICS[metric_name]
    expected_names = {_normalize_metric_name(slot.fact_name) for slot in definition.slots}
    return [
        fact_id
        for fact_id, fact in facts_by_id.items()
        if _normalize_metric_name(str(getattr(fact, "name", ""))) in expected_names
        and "startup_claim_id" not in getattr(fact, "metadata", {})
    ]


def _metric_diagnostic(metric_name: str, result: Any, input_fact_ids: list[UUID]) -> dict[str, Any]:
    calculation_id = getattr(result, "calculation_id", None)
    return {
        "metric_name": str(getattr(result, "metric_name", metric_name)),
        "status": _metric_status_value(getattr(result, "status", "unknown")),
        "warnings": [str(item) for item in getattr(result, "warnings", ())],
        "input_evidence_ids": [str(item) for item in input_fact_ids],
        "calculation_id": str(calculation_id) if calculation_id is not None else None,
    }


def _metric_status_value(status: object) -> str:
    if isinstance(status, MetricStatus):
        return status.value
    return str(getattr(status, "value", status))


def _normalize_metric_name(value: str) -> str:
    return value.strip().casefold().replace(" ", "_").replace("-", "_")


class AuditSpoolNodeAudit:
    def __init__(self, spool: AuditSpool) -> None:
        self._spool = spool

    def record(
        self,
        node_name: str,
        result: Any,
        state: dict[str, Any],
        *,
        attempt_count: int = 1,
        retry_count: int = 0,
        duration_ms: int | float | None = None,
        checkpoint_id: str | None = None,
        checkpoint_hash: str | None = None,
        tool: str | None = None,
    ) -> None:
        case_id = str(state.get("case_id", "unknown"))
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        attributes: dict[str, str | int | float | bool | None] = {
            "case_id": case_id,
            "node_name": node_name,
            "status": str(getattr(getattr(result, "status", None), "value", "unknown")),
            "evidence_count": len(getattr(result, "data_refs", [])),
            "attempt": attempt_count,
            "retry_count": retry_count,
            "schema_version": "startup_node_audit@1",
        }
        if duration_ms is not None:
            attributes["latency_ms"] = duration_ms
        if checkpoint_id is not None:
            attributes["checkpoint_id"] = checkpoint_id
        if checkpoint_hash is not None:
            attributes["checkpoint_hash"] = checkpoint_hash
        if tool is not None:
            attributes["tool"] = tool
        errors = [str(item) for item in getattr(result, "errors", [])]
        if errors:
            attributes["error_code"] = errors[0]
        self._spool.append(
            AuditEvent(
                schema_version="audit_event@1",
                event_id=str(uuid4()),
                timestamp_utc=timestamp,
                run_id=str(state.get("run_id", f"startup-{case_id}")),
                correlation_id=str(state.get("correlation_id", f"case-{case_id}")),
                span_name="analysis.module",
                event_type="span",
                attributes=attributes,
            )
        )


class MetricContractNodeTracer:
    def __init__(self, contract: MetricContract) -> None:
        self._contract = contract
        self.checkpoint_keys: set[str] = set()

    def record(self, **attributes: Any) -> None:
        safe_attrs = dict(attributes)
        duration_ms = safe_attrs.pop("duration_ms", 0)
        self._contract.record("node.outcome.count", 1, safe_attrs)
        self._contract.record("node.duration.ms", int(duration_ms), safe_attrs)

    def record_checkpoint_keys(self, keys: set[str]) -> None:
        self.checkpoint_keys = set(keys)


def _append_unique(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def _source_hashes(facts: tuple[EvidenceFact, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for fact in facts:
        source_hash = fact.supporting_text_hash
        if source_hash:
            hashes[str(fact.id)] = _sha256_ref(str(source_hash))
    return hashes


def _sha256_ref(value: str) -> str:
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _select_by_id[T](records: list[T], selected_ids: list[str]) -> tuple[T, ...]:
    selected = _uuid_set(selected_ids)
    return tuple(record for record in records if getattr(record, "id") in selected)


def _exact_profile(
    *,
    repository: Any,
    case_id: str,
    profile_id: str,
    profile_hash: str,
    profile_revision: int,
) -> StartupProfile:
    try:
        case_uuid = UUID(case_id)
        profile_uuid = UUID(profile_id)
    except ValueError as exc:
        raise StartupIntelligenceBindingError("startup_profile_identity_invalid") from exc
    try:
        profile = cast(StartupProfile, repository.get(profile_uuid))
        current = cast(StartupProfile, repository.get_current(case_uuid))
    except KeyError as exc:
        raise StartupIntelligenceBindingError("startup_profile_not_found") from exc
    if profile.case_id != case_uuid:
        raise StartupIntelligenceBindingError("startup_profile_case_mismatch")
    if profile.profile_hash != profile_hash:
        raise StartupIntelligenceBindingError("startup_profile_hash_mismatch")
    if profile.data_revision != profile_revision:
        raise StartupIntelligenceBindingError("startup_profile_revision_mismatch")
    if (
        current.profile_id != profile.profile_id
        or current.profile_hash != profile.profile_hash
        or current.data_revision != profile.data_revision
    ):
        raise StartupIntelligenceBindingError("startup_profile_not_current")
    return profile


def _uuid_list(values: list[str], code: str) -> list[UUID]:
    try:
        return [UUID(value) for value in values]
    except ValueError as exc:
        raise StartupIntelligenceBindingError(code) from exc


def _model_from_artifact[
    T: StartupReadinessSnapshot
    | StartupMarketResearchSnapshot
    | StartupProductValidationSnapshot
    | StartupGtmSnapshot
](
    artifact: dict[str, Any],
    model: type[T],
    code: str,
) -> T:
    payload = artifact.get("snapshot")
    if not isinstance(payload, dict):
        raise StartupReportProfileBindingError(code)
    try:
        return cast(T, model.model_validate(payload))
    except (TypeError, ValueError) as exc:
        raise StartupReportProfileBindingError(code) from exc


def _uuid_set(values: list[str]) -> set[UUID]:
    selected: set[UUID] = set()
    for value in values:
        try:
            selected.add(UUID(value))
        except ValueError:
            continue
    return selected


def _canonical_tuple(snapshot: ReportSnapshot) -> CanonicalReportSnapshot:
    return CanonicalReportSnapshot(
        snapshot_id=str(snapshot.id),
        snapshot_hash=snapshot.report_hash,
        snapshot_revision=snapshot.data_revision,
    )


def _ordered_startup_snapshot(snapshot: ReportSnapshot) -> ReportSnapshot:
    ordered = {
        key: snapshot.sections[key]
        for key in STARTUP_REPORT_SECTION_KEYS
        if key in snapshot.sections
    }
    ordered.update(
        {
            key: snapshot.sections[key]
            for key in sorted(snapshot.sections)
            if key not in ordered
        }
    )
    return snapshot.model_copy(update={"sections": ordered})
