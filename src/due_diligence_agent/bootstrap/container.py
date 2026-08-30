from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_FLOOR, Decimal
from functools import cache
from hashlib import sha256
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from langgraph.checkpoint.sqlite import SqliteSaver

from due_diligence_agent.adapters.documents.archive_inspector import ZipArchiveInspector
from due_diligence_agent.adapters.documents.spreadsheet_parser import SpreadsheetParser
from due_diligence_agent.adapters.http.fair_access import FairAccessLimiter
from due_diligence_agent.adapters.http.snapshot_cache import SnapshotCache
from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.local_storage.case_copilot_repositories import (
    LocalCaseAssetRepository,
    LocalCaseAssumptionRepository,
    LocalCaseCopilotThreadRepository,
    LocalCaseResearchJobRepository,
    LocalCaseResearchPlanRepository,
    LocalCaseScenarioRepository,
    LocalPublicBenchmarkRepository,
)
from due_diligence_agent.adapters.local_storage.repositories import (
    LocalApprovalRepository,
    LocalArtifactRepository,
    LocalCalculationRepository,
    LocalCaseRepository,
    LocalContradictionDecisionRepository,
    LocalContradictionRepository,
    LocalEvidenceRepository,
    LocalFindingRepository,
    LocalParsedStartupArtifactRepository,
    LocalReportRepository,
    LocalReviewRepository,
    LocalStartupClaimRepository,
    LocalStartupProfileRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.adapters.market_data.yfinance_demo import YFinanceDemoAdapter
from due_diligence_agent.adapters.news.gdelt import GdeltNewsAdapter
from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.metrics import MetricContract
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.adapters.openai.gateway import AsyncResponsesParseClient, OpenAIGateway
from due_diligence_agent.adapters.privacy.rules_redactor import RulesRedactor
from due_diligence_agent.adapters.retrieval.faiss_index import FaissEvidenceIndex
from due_diligence_agent.adapters.retrieval.fixture_embeddings import (
    DeterministicFixtureEmbeddingAdapter,
)
from due_diligence_agent.adapters.retrieval.local_embeddings import LocalEmbeddingAdapter
from due_diligence_agent.adapters.sec.edgar import SecEdgarAdapter
from due_diligence_agent.adapters.startup.deterministic_profile_extractor import (
    DeterministicStartupProfileExtractor,
)
from due_diligence_agent.adapters.startup.frozen_market_research import (
    FrozenStartupMarketResearchAdapter,
)
from due_diligence_agent.adapters.startup.profile_fragment_inventory import (
    PersistedStartupProfileFragmentInventory,
)
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy, DisclosureScope
from due_diligence_agent.application.policies.model_routing import ModelProfile, ModelRoutingPolicy
from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.application.services.case_asset_service import CaseAssetService
from due_diligence_agent.application.services.case_copilot_service import CaseCopilotService
from due_diligence_agent.application.services.case_fact_intake_service import (
    CaseFactIntakeService,
)
from due_diligence_agent.application.services.case_question_service import CaseQuestionService
from due_diligence_agent.application.services.case_research_job_service import (
    CaseResearchJobService,
    StartupResearchPortBenchmarkProvider,
)
from due_diligence_agent.application.services.case_service import CaseService
from due_diligence_agent.application.services.claim_extraction_service import ClaimExtractionService
from due_diligence_agent.application.services.data_room_service import DataRoomService
from due_diligence_agent.application.services.evidence_service import EvidenceService
from due_diligence_agent.application.services.explicit_contradiction_signal_service import (
    ExplicitContradictionSignalService,
)
from due_diligence_agent.application.services.filing_parsing_service import FilingParsingService
from due_diligence_agent.application.services.public_analysis_service import PublicAnalysisService
from due_diligence_agent.application.services.public_metric_service import PublicMetricService
from due_diligence_agent.application.services.report_service import ReportService
from due_diligence_agent.application.services.retrieval_service import RetrievalService
from due_diligence_agent.application.services.source_fact_contradiction_service import (
    SourceFactContradictionService,
)
from due_diligence_agent.application.services.startup_advisor_api_service import (
    StartupAdvisorApiContext,
    StartupAdvisorApiService,
)
from due_diligence_agent.application.services.startup_advisor_research_service import (
    StartupAdvisorResearchService,
)
from due_diligence_agent.application.services.startup_analysis_service import StartupAnalysisService
from due_diligence_agent.application.services.startup_disclosure_service import (
    StartupDisclosureService,
)
from due_diligence_agent.application.services.startup_market_research_service import (
    StartupMarketResearchService,
)
from due_diligence_agent.application.services.startup_metric_service import StartupMetricService
from due_diligence_agent.application.services.startup_parsing_service import StartupParsingService
from due_diligence_agent.application.services.startup_privacy_service import StartupPrivacyService
from due_diligence_agent.application.services.startup_profile_service import StartupProfileService
from due_diligence_agent.application.services.startup_scenario_service import (
    StartupScenarioService,
)
from due_diligence_agent.application.services.startup_spreadsheet_scalar_fact_extractor import (
    StartupSpreadsheetScalarFactExtractor,
)
from due_diligence_agent.application.services.table_normalization_service import (
    TableNormalizationService,
)
from due_diligence_agent.application.startup_advisor_recalculation import (
    is_founder_clarification_text,
    without_founder_clarification_marker,
)
from due_diligence_agent.config import OpenAIStartupSettings, Settings
from due_diligence_agent.domain.approvals.startup_disclosure import ClassifiedDisclosureSnapshot
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    CaseStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.documents.models import ParsedDocument, TextBlock
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import StartupClaim
from due_diligence_agent.domain.findings.models import Finding
from due_diligence_agent.domain.metrics.startup import STARTUP_METRICS
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.ports.collectors import (
    CompanyFactsSnapshot,
    CompanyIdentity,
    FilingArtifact,
    SourceSnapshot,
    SubmissionsSnapshot,
)
from due_diligence_agent.ports.repositories import ResearchAcquisitionMode
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.workflows.public_company.graph import build_public_graph
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus
from due_diligence_agent.workflows.startup.graph import StartupGraphDependencies
from due_diligence_agent.workflows.startup.ports import (
    AuditSpoolNodeAudit,
    MetricContractNodeTracer,
    StartupClaimRepositoryAdapter,
    StartupDocumentIntelligenceWorkflowAdapter,
    StartupGtmQueryRepositoryAdapter,
    StartupGtmWorkflowAdapter,
    StartupLineageRepositoryAdapter,
    StartupMarketResearchWorkflowAdapter,
    StartupMetricWorkflowAdapter,
    StartupProductValidationWorkflowAdapter,
    StartupProviderAnalysisResult,
    StartupReadinessWorkflowAdapter,
    StartupReflexionWorkflowAdapter,
    StartupReportRepositoryAdapter,
)
from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore
from due_diligence_agent.workflows.startup.tracing import CompositeNodeTracer

PUBLIC_US_FROZEN_FIXTURE_NAME = "public_us_frozen_v1"
STARTUP_MARKET_FIXTURE_NAME = "startup_market_research_v1"


@dataclass(frozen=True)
class LocalRepositories:
    database: SQLiteDatabase
    case_repository: LocalCaseRepository
    artifact_repository: LocalArtifactRepository
    evidence_repository: LocalEvidenceRepository
    calculation_repository: LocalCalculationRepository
    finding_repository: LocalFindingRepository
    startup_claim_repository: LocalStartupClaimRepository
    parsed_startup_artifact_repository: LocalParsedStartupArtifactRepository
    startup_profile_repository: LocalStartupProfileRepository
    contradiction_repository: LocalContradictionRepository
    approval_repository: LocalApprovalRepository
    report_repository: LocalReportRepository
    review_repository: LocalReviewRepository


@dataclass(frozen=True)
class CaseCopilotRepositories:
    assumptions: LocalCaseAssumptionRepository
    scenarios: LocalCaseScenarioRepository
    threads: LocalCaseCopilotThreadRepository
    research_plans: LocalCaseResearchPlanRepository
    research_jobs: LocalCaseResearchJobRepository
    public_benchmarks: LocalPublicBenchmarkRepository
    assets: LocalCaseAssetRepository


@dataclass(frozen=True)
class OpenAIStartupAIComponents:
    provider: Any
    profile_extractor: Any


@dataclass(frozen=True)
class PublicSources:
    sec: Any
    market: Any
    news: Any


@dataclass
class PublicGraphDependencySet:
    sec: Any
    market: Any
    news: Any
    artifact_repository: Any
    evidence_repository: Any
    artifact_store: Any
    retrieval: Any
    metric_service: Any
    guard: Any | None
    audit: Any | None
    async_sleeper: Any | None
    sync_sleeper: Any | None
    finding_repository: Any
    calculation_repository: Any
    contradiction_repository: Any
    report_repository: Any
    review_service: Any
    freeze_service: Any
    risk_analyzer: Any | None
    reflexion_reviewer: Any | None
    report_preparer: Any | None


@dataclass
class StartupGraphDependencySet:
    data_room: Any
    parser: Any
    privacy: Any
    disclosure: Any
    evidence: Any
    lineage: Any
    claims: Any
    document_intelligence: Any
    metrics: Any
    provider: Any
    reflexion: Any
    profile: Any
    readiness: Any
    market_research: Any
    product_validation: Any
    gtm: Any
    report: Any
    gate3: Any
    audit: Any | None
    tracer: Any | None
    deterministic_trace_usage: bool
    workflow_store: Any
    artifact_repository: Any
    _startup_disclosure_scope: DisclosureScope | None = None


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    repositories: LocalRepositories
    public_sources: PublicSources
    case_service: CaseService
    evidence_service: EvidenceService
    public_analysis_service: PublicAnalysisService
    report_service: ReportService
    retrieval_service: RetrievalService
    audit_spool: JsonlAuditSpool
    public_graph_dependencies: PublicGraphDependencySet
    public_graph: Any
    fixture_mode: bool
    _exit_stack: ExitStack
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        object.__setattr__(self, "_closed", True)
        self._exit_stack.close()


def build_container(settings: Settings, *, use_fixture_adapters: bool = False) -> AppContainer:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    stack = ExitStack()
    try:
        repositories = build_local_repositories(settings.data_dir / "metadata.sqlite3")
        stack.callback(repositories.database.close)
        artifact_store = LocalArtifactStore(settings.data_dir / "artifacts")
        audit_spool = JsonlAuditSpool(settings.data_dir / "audit-spool")
        audit_recorder = LocalAuditRecorder(audit_spool)
        sources = (
            build_fixture_sources(public_us_frozen_fixture_root(stack))
            if use_fixture_adapters
            else build_live_sources(settings)
        )
        stack.callback(_close_public_sources, sources)
        case_service = CaseService(repositories.case_repository)
        evidence_service = EvidenceService(
            artifact_repository=repositories.artifact_repository,
            evidence_repository=repositories.evidence_repository,
            contradiction_repository=repositories.contradiction_repository,
            finding_repository=repositories.finding_repository,
            calculation_repository=repositories.calculation_repository,
        )
        metric_service = PublicMetricService(
            evidence_repository=repositories.evidence_repository,
            calculation_repository=repositories.calculation_repository,
            clock=lambda: datetime.now(UTC),
        )
        retrieval = build_retrieval_service(
            settings=settings,
            artifact_store=artifact_store,
            use_fixture_adapters=use_fixture_adapters,
        )
        review_service = __import__(
            "due_diligence_agent.workflows.public_company.nodes.approvals",
            fromlist=["PublicReviewService"],
        ).PublicReviewService(repositories.review_repository)
        freeze_service = __import__(
            "due_diligence_agent.workflows.public_company.nodes.approvals",
            fromlist=["SnapshotFreezeService"],
        ).SnapshotFreezeService(repositories.review_repository)
        report_service = ReportService(
            approval_repository=repositories.approval_repository,
            current_data_revision=repositories.review_repository.current_data_revision,
            report_repository=repositories.report_repository,
        )
        graph_dependencies = PublicGraphDependencySet(
            sec=sources.sec,
            market=sources.market,
            news=sources.news,
            artifact_repository=repositories.artifact_repository,
            evidence_repository=repositories.evidence_repository,
            artifact_store=artifact_store,
            retrieval=retrieval,
            metric_service=metric_service,
            guard=None,
            audit=audit_recorder,
            async_sleeper=_no_async_sleep if use_fixture_adapters else asyncio.sleep,
            sync_sleeper=(lambda _seconds: None) if use_fixture_adapters else time.sleep,
            finding_repository=repositories.finding_repository,
            calculation_repository=repositories.calculation_repository,
            contradiction_repository=repositories.contradiction_repository,
            report_repository=repositories.report_repository,
            review_service=review_service,
            freeze_service=freeze_service,
            risk_analyzer=None,
            reflexion_reviewer=None,
            report_preparer=None,
        )
        checkpointer = stack.enter_context(
            SqliteSaver.from_conn_string(str(settings.data_dir / "checkpoints.sqlite3"))
        )
        public_graph = build_public_graph(graph_dependencies, checkpointer=checkpointer)
        public_analysis_service = PublicAnalysisService(
            public_graph,
            case_repository=repositories.case_repository,
            evidence_repository=repositories.evidence_repository,
            calculation_repository=repositories.calculation_repository,
            finding_repository=repositories.finding_repository,
            contradiction_repository=repositories.contradiction_repository,
            report_service=report_service,
            report_repository=repositories.report_repository,
        )
        graph_dependencies.report_preparer = public_analysis_service._build_current_draft
        return AppContainer(
            settings=settings,
            repositories=repositories,
            public_sources=sources,
            case_service=case_service,
            evidence_service=evidence_service,
            public_analysis_service=public_analysis_service,
            report_service=report_service,
            retrieval_service=retrieval,
            audit_spool=audit_spool,
            public_graph_dependencies=graph_dependencies,
            public_graph=public_graph,
            fixture_mode=use_fixture_adapters,
            _exit_stack=stack,
        )
    except Exception:
        stack.close()
        raise


def build_local_repositories(path: Path) -> LocalRepositories:
    db = SQLiteDatabase(path)
    artifact_repository = LocalArtifactRepository(db)
    evidence_repository = LocalEvidenceRepository(db)
    calculation_repository = LocalCalculationRepository(db)
    finding_repository = LocalFindingRepository(db)
    contradiction_repository = LocalContradictionRepository(db)
    startup_claim_repository = LocalStartupClaimRepository(db)
    parsed_startup_artifact_repository = LocalParsedStartupArtifactRepository(db)
    startup_profile_repository = LocalStartupProfileRepository(db)
    approval_repository = LocalApprovalRepository(db)
    decision_repository = LocalContradictionDecisionRepository(db)
    report_repository = LocalReportRepository(db)
    return LocalRepositories(
        database=db,
        case_repository=LocalCaseRepository(db),
        artifact_repository=artifact_repository,
        evidence_repository=evidence_repository,
        calculation_repository=calculation_repository,
        finding_repository=finding_repository,
        startup_claim_repository=startup_claim_repository,
        parsed_startup_artifact_repository=parsed_startup_artifact_repository,
        startup_profile_repository=startup_profile_repository,
        contradiction_repository=contradiction_repository,
        approval_repository=approval_repository,
        report_repository=report_repository,
        review_repository=LocalReviewRepository(
            artifact_repository=artifact_repository,
            evidence_repository=evidence_repository,
            calculation_repository=calculation_repository,
            finding_repository=finding_repository,
            contradiction_repository=contradiction_repository,
            report_repository=report_repository,
            approval_repository=approval_repository,
            decision_repository=decision_repository,
        ),
    )


def build_startup_analysis_composer(
    data_dir: Path,
    *,
    inbox_root: Path | None = None,
    provider: Any | None = None,
    provider_factory: Callable[[LocalRepositories, JsonlAuditSpool], Any | None] | None = None,
    profile_extractor: Any | None = None,
    profile_extractor_factory: Callable[[LocalRepositories, JsonlAuditSpool], Any | None]
    | None = None,
    ai_components_factory: Callable[
        [LocalRepositories, JsonlAuditSpool], OpenAIStartupAIComponents | None
    ]
    | None = None,
    external_node_tracer: Any | None = None,
) -> StartupAnalysisService:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    artifact_store = LocalArtifactStore(data_dir / "startup-artifacts")
    audit_spool = JsonlAuditSpool(data_dir / "startup-audit-spool")
    if (provider is None or profile_extractor is None) and ai_components_factory is not None:
        ai_components = ai_components_factory(repositories, audit_spool)
        if ai_components is not None:
            if provider is None:
                provider = ai_components.provider
            if profile_extractor is None:
                profile_extractor = ai_components.profile_extractor
    if provider is None and provider_factory is not None:
        provider = provider_factory(repositories, audit_spool)
    if profile_extractor is None and profile_extractor_factory is not None:
        profile_extractor = profile_extractor_factory(repositories, audit_spool)
    privacy_service = StartupPrivacyService(
        artifact_store=artifact_store,
        redactor=RulesRedactor(),
        egress_policy=DataEgressPolicy(),
        trace_sanitizer=StrictTraceSanitizer(),
    )
    spreadsheet_parser = SpreadsheetParser(
        artifact_store=artifact_store,
        normalizer=TableNormalizationService(
            artifact_store=artifact_store,
            database_path=data_dir / "startup-normalized.duckdb",
        ),
    )
    disclosure_service = StartupDisclosureService(
        approval_repository=repositories.approval_repository,
        audit_spool=audit_spool,
        clock=lambda: datetime.now(UTC),
    )
    metric_service = StartupMetricService(
        evidence_repository=repositories.evidence_repository,
        calculation_repository=repositories.calculation_repository,
        clock=lambda: datetime.now(UTC),
    )
    workflow_store = SQLiteStartupWorkflowRuntimeStore(data_dir / "startup-runtime.sqlite3")
    report_port = _startup_report_port(
        repositories,
        data_dir,
        workflow_store=workflow_store,
        audit_spool=audit_spool,
    )
    parser = _StartupParsingWorkflowPort(
        artifact_store,
        artifact_repository=repositories.artifact_repository,
        parsed_artifact_repository=repositories.parsed_startup_artifact_repository,
        spreadsheet_parser=spreadsheet_parser,
    )
    profile_fragment_inventory = PersistedStartupProfileFragmentInventory(
        workflow_store=workflow_store,
        parser=parser,
        artifact_repository=repositories.artifact_repository,
        artifact_store=artifact_store,
    )
    profile_service = StartupProfileService(
        case_repository=repositories.case_repository,
        artifact_repository=repositories.artifact_repository,
        parsed_artifact_repository=repositories.parsed_startup_artifact_repository,
        evidence_repository=repositories.evidence_repository,
        startup_claim_repository=repositories.startup_claim_repository,
        contradiction_repository=repositories.contradiction_repository,
        startup_profile_repository=repositories.startup_profile_repository,
        deterministic_extractor=DeterministicStartupProfileExtractor(),
        external_extractor=profile_extractor,
        fragment_inventory=profile_fragment_inventory,
    )
    profile_service.redaction_policy_version = privacy_service.policy_version
    metric_tracer = MetricContractNodeTracer(MetricContract())
    dependencies = StartupGraphDependencySet(
        data_room=_StartupDataRoomWorkflowPort(
            data_room=DataRoomService(
                artifact_store=artifact_store,
                artifact_repository=repositories.artifact_repository,
                archive_inspector=ZipArchiveInspector(staging_root=data_dir / "startup-staging"),
                quarantine_root=data_dir / "startup-quarantine",
                audit_spool=audit_spool,
            ),
            inbox_root=inbox_root if inbox_root is not None else data_dir / "inbox",
            case_repository=repositories.case_repository,
            artifact_store=artifact_store,
            artifact_repository=repositories.artifact_repository,
        ),
        parser=parser,
        privacy=_StartupPrivacyWorkflowPort(privacy_service, parser=parser),
        disclosure=disclosure_service,
        evidence=_StartupEvidenceFromParsedDocumentsWorkflowPort(
            repositories.evidence_repository,
            repositories.startup_claim_repository,
            parser=parser,
            contradiction_repository=repositories.contradiction_repository,
        ),
        lineage=StartupLineageRepositoryAdapter(repositories.review_repository),
        claims=StartupClaimRepositoryAdapter(
            repositories.startup_claim_repository,
            evidence_repository=repositories.evidence_repository,
            calculation_repository=repositories.calculation_repository,
            contradiction_repository=repositories.contradiction_repository,
        ),
        document_intelligence=StartupDocumentIntelligenceWorkflowAdapter(
            workflow_store=workflow_store,
        ),
        metrics=StartupMetricWorkflowAdapter(
            metric_service,
            metric_names=tuple(STARTUP_METRICS),
            evidence_repository=repositories.evidence_repository,
        ),
        readiness=StartupReadinessWorkflowAdapter(
            startup_profile_repository=repositories.startup_profile_repository,
            workflow_store=workflow_store,
        ),
        market_research=StartupMarketResearchWorkflowAdapter(
            startup_profile_repository=repositories.startup_profile_repository,
            workflow_store=workflow_store,
            research_port=FrozenStartupMarketResearchAdapter.from_fixture_dir(
                startup_market_fixture_root()
            ),
        ),
        provider=_StartupProviderWorkflowPort(
            provider=provider,
            finding_repository=repositories.finding_repository,
        ),
        reflexion=StartupReflexionWorkflowAdapter(
            finding_repository=repositories.finding_repository,
            contradiction_repository=repositories.contradiction_repository,
            workflow_store=workflow_store,
        ),
        product_validation=StartupProductValidationWorkflowAdapter(
            startup_profile_repository=repositories.startup_profile_repository,
            workflow_store=workflow_store,
        ),
        gtm=StartupGtmWorkflowAdapter(
            startup_profile_repository=repositories.startup_profile_repository,
            workflow_store=workflow_store,
        ),
        profile=profile_service,
        report=report_port,
        gate3=None,
        audit=AuditSpoolNodeAudit(audit_spool),
        tracer=(
            CompositeNodeTracer(metric_tracer, external_node_tracer)
            if external_node_tracer is not None
            else metric_tracer
        ),
        deterministic_trace_usage=isinstance(provider, _DeterministicStartupProvider)
        and isinstance(profile_extractor, DeterministicStartupProfileExtractor),
        workflow_store=workflow_store,
        artifact_repository=repositories.artifact_repository,
    )
    typed_dependencies: StartupGraphDependencies = dependencies
    return StartupAnalysisService(
        dependencies=typed_dependencies,
        checkpoint_path=data_dir / "startup-checkpoints.sqlite3",
    )


def build_deterministic_startup_analysis_composer(
    data_dir: Path,
    *,
    inbox_root: Path | None = None,
    external_node_tracer: Any | None = None,
) -> StartupAnalysisService:
    return build_startup_analysis_composer(
        data_dir,
        inbox_root=inbox_root,
        provider=_DeterministicStartupProvider(),
        profile_extractor=DeterministicStartupProfileExtractor(),
        external_node_tracer=external_node_tracer,
    )


def build_openai_startup_components(
    *,
    settings: OpenAIStartupSettings,
    repositories: LocalRepositories,
    audit_spool: JsonlAuditSpool,
    llm_call_recorder: Callable[..., None] | None = None,
) -> OpenAIStartupAIComponents | None:
    if settings.openai_api_key is None:
        return None

    from openai import AsyncOpenAI

    from due_diligence_agent.adapters.openai.startup_profile_extractor import (
        OpenAIStartupProfileExtractor,
    )
    from due_diligence_agent.adapters.openai.startup_provider import OpenAIStartupProvider

    model_profile = ModelProfile(
        provider="openai",
        model=settings.model,
        role="startup_due_diligence",
    )
    max_tokens = settings.max_input_tokens + settings.max_output_tokens
    worst_case_usd_cost = settings.per_call_worst_case_usd_cost
    case_token_limit = _startup_openai_case_token_limit(settings)
    gateway = OpenAIGateway(
        responses_client=cast(
            AsyncResponsesParseClient,
            AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.timeout_seconds,
                max_retries=settings.max_retries,
            ).responses,
        ),
        egress_policy=DataEgressPolicy(),
        routing_policy=ModelRoutingPolicy(
            default_profile=model_profile,
            high_reasoning_profile=model_profile,
        ),
        budget_guard=BudgetGuard(
            default_token_limit=case_token_limit,
            default_usd_limit=Decimal(settings.per_case_usd_cap),
            persistence_path=repositories.database.path.with_name("startup-openai-budget.sqlite3"),
        ),
        audit_spool=audit_spool,
        sanitizer=StrictTraceSanitizer(),
        max_output_tokens=settings.max_output_tokens,
        usage_cost_calculator=lambda usage: _startup_openai_usage_cost(settings, usage),
        llm_call_recorder=llm_call_recorder,
    )
    provider = OpenAIStartupProvider(
        gateway=gateway,
        evidence_repository=repositories.evidence_repository,
        calculation_repository=repositories.calculation_repository,
        worst_case_tokens=max_tokens,
        worst_case_usd_cost=worst_case_usd_cost,
    )
    profile_extractor = OpenAIStartupProfileExtractor(
        gateway=gateway,
        worst_case_tokens=max_tokens,
        worst_case_usd_cost=worst_case_usd_cost,
    )
    return OpenAIStartupAIComponents(
        provider=provider,
        profile_extractor=profile_extractor,
    )


def _startup_openai_case_token_limit(settings: OpenAIStartupSettings) -> int:
    cheapest_per_million = min(
        settings.input_usd_per_million_tokens,
        settings.output_usd_per_million_tokens,
    )
    if cheapest_per_million <= 0:
        return settings.max_input_tokens + settings.max_output_tokens
    return max(
        settings.max_input_tokens + settings.max_output_tokens,
        int(
            (Decimal(settings.per_case_usd_cap) * Decimal(1_000_000) / cheapest_per_million)
            .to_integral_value(rounding=ROUND_FLOOR)
        ),
    )


def _startup_openai_usage_cost(settings: OpenAIStartupSettings, usage: Any) -> Decimal:
    input_tokens = Decimal(int(getattr(usage, "input_tokens", 0)))
    output_tokens = Decimal(int(getattr(usage, "output_tokens", 0)))
    total_tokens = Decimal(int(getattr(usage, "total_tokens", 0)))
    unattributed_tokens = max(total_tokens - input_tokens - output_tokens, Decimal(0))
    unattributed_rate = max(
        settings.input_usd_per_million_tokens,
        settings.output_usd_per_million_tokens,
    )
    return (
        input_tokens * settings.input_usd_per_million_tokens
        + output_tokens * settings.output_usd_per_million_tokens
        + unattributed_tokens * unattributed_rate
    ) / Decimal(1_000_000)


def build_openai_startup_provider(
    *,
    settings: OpenAIStartupSettings,
    repositories: LocalRepositories,
    audit_spool: JsonlAuditSpool,
) -> Any | None:
    components = build_openai_startup_components(
        settings=settings,
        repositories=repositories,
        audit_spool=audit_spool,
    )
    if components is None:
        return None
    return components.provider


def build_startup_report_port(data_dir: Path) -> StartupReportRepositoryAdapter:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    workflow_store = SQLiteStartupWorkflowRuntimeStore(data_dir / "startup-runtime.sqlite3")
    audit_spool = JsonlAuditSpool(data_dir / "startup-audit-spool")
    return _startup_report_port(
        repositories,
        data_dir,
        workflow_store=workflow_store,
        audit_spool=audit_spool,
    )


def build_startup_case_revision_port(data_dir: Path) -> _StartupCaseRevisionRepositoryAdapter:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    return _StartupCaseRevisionRepositoryAdapter(repositories.case_repository)


def build_case_copilot_repositories(data_dir: Path) -> CaseCopilotRepositories:
    return _cached_case_copilot_repositories(data_dir.resolve())


def build_case_fact_intake_service(data_dir: Path) -> CaseFactIntakeService:
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    copilot_repositories = build_case_copilot_repositories(data_dir)
    return CaseFactIntakeService(
        case_repository=repositories.case_repository,
        assumption_repository=copilot_repositories.assumptions,
        question_service_factory=lambda _answers: CaseQuestionService(
            case_repository=repositories.case_repository,
            profile_repository=repositories.startup_profile_repository,
            assumption_repository=copilot_repositories.assumptions,
            contradiction_repository=repositories.contradiction_repository,
        ),
    )


def build_case_copilot_service(
    data_dir: Path,
    *,
    workflow_store: SQLiteStartupWorkflowRuntimeStore,
    inbox_root: Path,
    research_provider: Any | None = None,
    live_research_port: Any | None = None,
    acquisition_mode: ResearchAcquisitionMode | None = None,
    analysis_revision_starter: Callable[..., None] | None = None,
) -> CaseCopilotService:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    copilot_repositories = build_case_copilot_repositories(data_dir)
    question_service = CaseQuestionService(
        case_repository=repositories.case_repository,
        profile_repository=repositories.startup_profile_repository,
        assumption_repository=copilot_repositories.assumptions,
        contradiction_repository=repositories.contradiction_repository,
    )
    scenario_service = StartupScenarioService(
        case_repository=repositories.case_repository,
        assumption_repository=copilot_repositories.assumptions,
        scenario_repository=copilot_repositories.scenarios,
        public_benchmark_repository=copilot_repositories.public_benchmarks,
    )
    research_providers: dict[ResearchAcquisitionMode, Any] = {
        "deterministic_offline_fixture": DeterministicCaseCopilotBenchmarkProvider()
    }
    configured_research_provider = research_provider
    configured_acquisition_mode = acquisition_mode
    if configured_research_provider is None and live_research_port is not None:
        configured_research_provider = StartupResearchPortBenchmarkProvider(live_research_port)
        configured_acquisition_mode = "live_public_research"
    if configured_research_provider is not None and configured_acquisition_mode not in (
        None,
        "provider_unconfigured",
    ):
        research_providers[configured_acquisition_mode] = configured_research_provider
    elif os.environ.get("FOUNDER_CASE_FIXTURE_MODE") == "deterministic_offline":
        configured_research_provider = DeterministicCaseCopilotBenchmarkProvider()
        configured_acquisition_mode = "deterministic_offline_fixture"
        research_providers[configured_acquisition_mode] = configured_research_provider
    research_service = CaseResearchJobService(
        case_repository=repositories.case_repository,
        plan_repository=copilot_repositories.research_plans,
        job_repository=copilot_repositories.research_jobs,
        public_benchmark_repository=copilot_repositories.public_benchmarks,
        scenario_repository=copilot_repositories.scenarios,
        profile_repository=repositories.startup_profile_repository,
        research_providers=cast(dict[Any, Any], research_providers),
    )
    return CaseCopilotService(
        workflow_store=workflow_store,
        read_model_workflow_store=SQLiteStartupWorkflowRuntimeStore(
            data_dir / "startup-runtime.sqlite3"
        ),
        inbox_root=inbox_root,
        case_repository=repositories.case_repository,
        profile_repository=repositories.startup_profile_repository,
        assumption_repository=copilot_repositories.assumptions,
        thread_repository=copilot_repositories.threads,
        fact_intake_service=build_case_fact_intake_service(data_dir),
        question_service=question_service,
        scenario_service=scenario_service,
        scenario_repository=copilot_repositories.scenarios,
        research_service=research_service,
        public_benchmark_repository=copilot_repositories.public_benchmarks,
        analysis_revision_starter=analysis_revision_starter,
    )


def build_case_asset_service(data_dir: Path) -> CaseAssetService:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    copilot_repositories = build_case_copilot_repositories(data_dir)
    scenario_service = StartupScenarioService(
        case_repository=repositories.case_repository,
        assumption_repository=copilot_repositories.assumptions,
        scenario_repository=copilot_repositories.scenarios,
        public_benchmark_repository=copilot_repositories.public_benchmarks,
    )
    return CaseAssetService(
        case_repository=repositories.case_repository,
        asset_repository=copilot_repositories.assets,
        scenario_repository=copilot_repositories.scenarios,
        scenario_service=scenario_service,
        profile_repository=repositories.startup_profile_repository,
        gtm_query=build_startup_gtm_query_port(data_dir),
        report_query=build_startup_report_port(data_dir),
        report_repository=repositories.report_repository,
    )


class DeterministicCaseCopilotBenchmarkProvider:
    """Offline-only public benchmark provider for local Case Copilot smoke runs."""

    def collect(self, plan: Any) -> list[dict[str, object]]:
        source_ref = uuid5(
            NAMESPACE_URL,
            f"case-copilot-deterministic-benchmark:{plan.case_id}:{plan.plan_hash}",
        )
        input_key = (
            "monthly_price" if plan.focus_key == "public_pricing_analogs" else "acquisition_spend"
        )
        return [
            {
                "input_key": input_key,
                "provenance": CaseValueKind.PUBLIC_BENCHMARK.value,
                "url": "https://example.com/case-copilot-deterministic-benchmark",
                "publisher": "Deterministic Case Copilot Fixture",
                "publication_date": "2026-08-01",
                "retrieval_date": "2026-08-23",
                "as_of": "2026-08-01",
                "source_class": "industry_report",
                "confidence": "medium",
                "range_low": "1000",
                "range_high": "2000",
                "unit": "KZT",
                "period": "month",
                "formula": "deterministic public benchmark range",
                "dependencies": ("public comparable companies",),
                "validation_plan": (
                    "Use only as external context until founder-specific evidence exists."
                ),
                "source_refs": (source_ref,),
                "rationale": "Deterministic cited public benchmark for local smoke verification.",
            }
        ]


@cache
def _cached_case_copilot_repositories(data_dir: Path) -> CaseCopilotRepositories:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")

    def current_revision(case_id: UUID) -> int:
        return int(repositories.case_repository.get(case_id).data_revision)

    return CaseCopilotRepositories(
        assumptions=LocalCaseAssumptionRepository(
            data_dir,
            current_revision=current_revision,
        ),
        scenarios=LocalCaseScenarioRepository(
            data_dir,
            current_revision=current_revision,
        ),
        threads=LocalCaseCopilotThreadRepository(
            data_dir,
            current_revision=current_revision,
        ),
        research_plans=LocalCaseResearchPlanRepository(
            data_dir,
            current_revision=current_revision,
        ),
        research_jobs=LocalCaseResearchJobRepository(
            data_dir,
            current_revision=current_revision,
        ),
        public_benchmarks=LocalPublicBenchmarkRepository(
            data_dir,
            current_revision=current_revision,
        ),
        assets=LocalCaseAssetRepository(
            data_dir,
            current_revision=current_revision,
        ),
    )


def build_startup_profile_query_port(data_dir: Path) -> LocalStartupProfileRepository:
    data_dir.mkdir(parents=True, exist_ok=True)
    repositories = build_local_repositories(data_dir / "startup-metadata.sqlite3")
    return repositories.startup_profile_repository


def build_startup_advisor_research_service(
    *,
    profile_repository: Any,
    live_research_port: Any | None = None,
    fallback_research_port: Any | None = None,
    case_research_service: Any | None = None,
    audit_spool: Any | None = None,
    clock: Callable[[], datetime] | None = None,
) -> StartupAdvisorResearchService:
    """Compose the advisor side path without importing or constructing a live SDK."""

    fallback = fallback_research_port
    if fallback is None:
        fallback = FrozenStartupMarketResearchAdapter.from_fixture_dir(startup_market_fixture_root())
    return StartupAdvisorResearchService(
        profile_repository=profile_repository,
        market_research_service=StartupMarketResearchService(clock=clock),
        live_research_port=live_research_port,
        fallback_research_port=fallback,
        case_research_service=case_research_service,
        audit_spool=audit_spool,
    )


def build_openai_startup_advisor_research_service(
    *,
    settings: OpenAIStartupSettings,
    repositories: LocalRepositories,
    audit_spool: JsonlAuditSpool,
    clock: Callable[[], datetime] | None = None,
    llm_call_recorder: Callable[..., None] | None = None,
) -> StartupAdvisorResearchService:
    """Opt-in production composition for public web research."""

    live_research_port = build_openai_startup_research_port(
        settings=settings,
        repositories=repositories,
        audit_spool=audit_spool,
        clock=clock,
        llm_call_recorder=llm_call_recorder,
    )
    research_provider = (
        StartupResearchPortBenchmarkProvider(live_research_port)
        if live_research_port is not None
        else None
    )
    return build_startup_advisor_research_service(
        profile_repository=repositories.startup_profile_repository,
        live_research_port=live_research_port,
        case_research_service=_build_case_research_job_service_for_advisor(
            repositories=repositories,
            research_provider=research_provider,
            clock=clock,
        ),
        audit_spool=audit_spool,
        clock=clock,
    )


def _build_case_research_job_service_for_advisor(
    *,
    repositories: Any,
    research_provider: Any | None,
    clock: Callable[[], datetime] | None = None,
) -> CaseResearchJobService | None:
    database = getattr(repositories, "database", None)
    database_path = getattr(database, "path", None)
    case_repository = getattr(repositories, "case_repository", None)
    if database_path is None or case_repository is None:
        return None
    data_dir = Path(database_path).parent
    copilot_repositories = build_case_copilot_repositories(data_dir)
    return CaseResearchJobService(
        case_repository=case_repository,
        plan_repository=copilot_repositories.research_plans,
        job_repository=copilot_repositories.research_jobs,
        public_benchmark_repository=copilot_repositories.public_benchmarks,
        scenario_repository=copilot_repositories.scenarios,
        research_provider=research_provider,
        acquisition_mode=(
            "live_public_research"
            if research_provider is not None
            else "provider_unconfigured"
        ),
        profile_repository=repositories.startup_profile_repository,
        clock=clock,
    )


def build_openai_startup_research_port(
    *,
    settings: OpenAIStartupSettings,
    repositories: LocalRepositories,
    audit_spool: JsonlAuditSpool,
    clock: Callable[[], datetime] | None = None,
    llm_call_recorder: Callable[..., None] | None = None,
) -> Any | None:
    """Shared opt-in public web research port for advisor and Case Copilot."""

    if settings.openai_api_key is None:
        return None
    from due_diligence_agent.adapters.openai.startup_web_research import (
        STARTUP_PUBLIC_RESEARCH_WORST_CASE_TOKENS,
        OpenAIStartupWebResearchAdapter,
    )

    return OpenAIStartupWebResearchAdapter.from_openai(
        api_key=settings.openai_api_key.get_secret_value(),
        budget_guard=BudgetGuard(
            default_token_limit=(
                max(
                    settings.max_input_tokens + min(settings.max_output_tokens, 600),
                    STARTUP_PUBLIC_RESEARCH_WORST_CASE_TOKENS,
                )
            ),
            default_usd_limit=Decimal(settings.per_case_usd_cap),
            persistence_path=repositories.database.path.with_name(
                "startup-openai-public-research-budget.sqlite3"
            ),
        ),
        audit_spool=audit_spool,
        clock=clock,
        usage_cost_calculator=lambda usage: _startup_openai_usage_cost(settings, usage),
        llm_call_recorder=llm_call_recorder,
    )


def build_startup_advisor_api_service(
    *,
    data_dir: Path,
    deterministic_data_dir: Path,
    workflow_store: Any,
    openai_settings: OpenAIStartupSettings,
    recalculation_port: Any | None = None,
    llm_call_recorder: Callable[..., None] | None = None,
) -> StartupAdvisorApiService:
    """Compose the restart-safe advisor facade over existing local boundaries."""

    def context_for(path: Path, *, allow_live: bool) -> StartupAdvisorApiContext:
        path.mkdir(parents=True, exist_ok=True)
        repositories = build_local_repositories(path / "startup-metadata.sqlite3")
        intelligence_store = SQLiteStartupWorkflowRuntimeStore(path / "startup-runtime.sqlite3")
        audit_spool = JsonlAuditSpool(path / "startup-audit-spool")
        research_service = (
            build_openai_startup_advisor_research_service(
                settings=openai_settings,
                repositories=repositories,
                audit_spool=audit_spool,
                llm_call_recorder=llm_call_recorder,
            )
            if allow_live
            else build_startup_advisor_research_service(
                profile_repository=repositories.startup_profile_repository,
                case_research_service=_build_case_research_job_service_for_advisor(
                    repositories=repositories,
                    research_provider=None,
                ),
                audit_spool=audit_spool,
            )
        )
        return StartupAdvisorApiContext(
            case_repository=repositories.case_repository,
            profile_repository=repositories.startup_profile_repository,
            report_repository=repositories.report_repository,
            calculation_repository=repositories.calculation_repository,
            contradiction_repository=repositories.contradiction_repository,
            gtm_repository=StartupGtmQueryRepositoryAdapter(workflow_store=intelligence_store),
            intelligence_store=intelligence_store,
            research_service=research_service,
            evidence_repository=repositories.evidence_repository,
        )

    return StartupAdvisorApiService(
        workflow_store=workflow_store,
        live_context=context_for(data_dir, allow_live=True),
        deterministic_context=context_for(
            deterministic_data_dir,
            allow_live=False,
        ),
        recalculation_port=recalculation_port,
    )


def build_startup_gtm_query_port(data_dir: Path) -> StartupGtmQueryRepositoryAdapter:
    data_dir.mkdir(parents=True, exist_ok=True)
    return StartupGtmQueryRepositoryAdapter(
        workflow_store=SQLiteStartupWorkflowRuntimeStore(data_dir / "startup-runtime.sqlite3")
    )


def _startup_report_port(
    repositories: LocalRepositories,
    data_dir: Path,
    *,
    workflow_store: Any | None = None,
    audit_spool: JsonlAuditSpool,
) -> StartupReportRepositoryAdapter:
    current_data_revision = _canonical_case_data_revision(repositories)
    report_service = ReportService(
        approval_repository=repositories.approval_repository,
        current_data_revision=current_data_revision,
        report_repository=repositories.report_repository,
    )
    return StartupReportRepositoryAdapter(
        case_repository=repositories.case_repository,
        startup_claim_repository=repositories.startup_claim_repository,
        evidence_repository=repositories.evidence_repository,
        calculation_repository=repositories.calculation_repository,
        finding_repository=repositories.finding_repository,
        contradiction_repository=repositories.contradiction_repository,
        startup_profile_repository=repositories.startup_profile_repository,
        report_repository=repositories.report_repository,
        approval_repository=repositories.approval_repository,
        current_data_revision=current_data_revision,
        report_service=report_service,
        output_dir=data_dir / "startup-reports",
        workflow_store=workflow_store,
        audit_spool=audit_spool,
        clock=lambda: datetime.now(UTC),
    )


def _canonical_case_data_revision(repositories: LocalRepositories) -> Callable[[UUID], int]:
    def current_data_revision(case_id: UUID) -> int:
        return int(repositories.case_repository.get(case_id).data_revision)

    return current_data_revision


class _StartupCaseRevisionRepositoryAdapter:
    def __init__(self, case_repository: LocalCaseRepository) -> None:
        self._case_repository = case_repository

    def current_revision(self, case_id: str) -> int:
        case_uuid = UUID(case_id)
        try:
            return int(self._case_repository.get(case_uuid).data_revision)
        except KeyError:
            return 0

    def advance_revision(
        self,
        case_id: str,
        *,
        expected_current_revision: int,
        document_ids: list[str],
        source_refs: list[dict[str, str]],
        metadata: dict[str, str],
    ) -> int:
        del document_ids, source_refs, metadata
        if expected_current_revision < 0:
            raise ValueError("case_revision_conflict")
        case_uuid = UUID(case_id)
        now = datetime.now(UTC)
        if expected_current_revision == 0:
            try:
                self._case_repository.get(case_uuid)
            except KeyError:
                self._case_repository.add(
                    _startup_case(case_uuid).model_copy(
                        update={"data_revision": 1, "updated_at": now}
                    )
                )
                return 1
            raise ValueError("case_revision_conflict")
        try:
            current = self._case_repository.get(case_uuid)
        except KeyError as exc:
            raise ValueError("case_revision_conflict") from exc
        if int(current.data_revision) != expected_current_revision:
            raise ValueError("case_revision_conflict")
        updated = current.model_copy(
            update={
                "data_revision": expected_current_revision + 1,
                "updated_at": now,
            }
        )
        try:
            self._case_repository.advance_data_revision(
                case_uuid,
                expected_revision=expected_current_revision,
                updated_case=updated,
            )
        except ValueError as exc:
            raise ValueError("case_revision_conflict") from exc
        return expected_current_revision + 1


class _StartupDataRoomWorkflowPort:
    def __init__(
        self,
        *,
        data_room: DataRoomService,
        inbox_root: Path,
        case_repository: LocalCaseRepository,
        artifact_store: LocalArtifactStore,
        artifact_repository: LocalArtifactRepository,
    ) -> None:
        self._data_room = data_room
        self._inbox_root = inbox_root.resolve()
        self._case_repository = case_repository
        self._artifact_store = artifact_store
        self._artifact_repository = artifact_repository

    def ingest(
        self,
        *,
        case_id: str,
        source_refs: list[dict[str, str]],
        data_revision: int,
    ) -> dict[str, object]:
        case_uuid = UUID(case_id)
        try:
            case = self._case_repository.get(case_uuid)
        except KeyError:
            case = _startup_case(case_uuid).model_copy(update={"data_revision": data_revision})
            self._case_repository.add(case)
        if int(case.data_revision) != data_revision:
            raise ValueError("startup_case_data_revision_mismatch")
        resolved = [_resolve_source_ref(self._inbox_root, case_uuid, item) for item in source_refs]
        existing = self._existing_artifacts_by_source_hash(case_uuid)
        new_sources = [path for content_hash, path in resolved if content_hash not in existing]
        inventory = self._data_room.ingest(case_uuid, new_sources) if new_sources else None
        accepted = [
            existing_artifact
            for content_hash, _path in resolved
            for existing_artifact in existing.get(content_hash, ())
        ]
        if inventory is not None:
            accepted.extend(inventory.accepted)
        accepted_by_id = {str(artifact.id): artifact for artifact in accepted}
        quarantine = []
        if inventory is not None:
            quarantine = [
                {
                    "content_hash": item.content_hash,
                    "reason": item.reason,
                    "byte_size": item.byte_size,
                }
                for item in inventory.quarantined
            ]
        inventory_id = (
            "inventory-"
            + sha256(
                "|".join(
                    (
                        str(case_uuid),
                        str(data_revision),
                        *[content_hash for content_hash, _path in resolved],
                    )
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        return {
            "inventory_id": inventory_id,
            "artifact_ids": sorted(accepted_by_id),
            "quarantine": quarantine,
        }

    def _existing_artifacts_by_source_hash(
        self,
        case_id: UUID,
    ) -> dict[str, tuple[Any, ...]]:
        existing: dict[str, list[Any]] = {}
        for artifact in self._artifact_repository.list_for_case(case_id):
            existing.setdefault(artifact.source_snapshot_hash, []).append(artifact)
        return {key: tuple(value) for key, value in existing.items()}


def _resolve_source_ref(
    inbox_root: Path,
    case_id: UUID,
    source_ref: dict[str, str],
) -> tuple[str, Path]:
    document_id = source_ref.get("document_id")
    private_name = source_ref.get("private_name")
    content_hash = source_ref.get("content_sha256")
    if not isinstance(document_id, str) or not re.fullmatch(r"doc-\d{4}", document_id):
        raise ValueError("startup_source_ref_document_id_invalid")
    if not isinstance(private_name, str) or not re.fullmatch(
        rf"{re.escape(document_id)}\.(pdf|docx|png|jpg|jpeg|csv|xlsx|txt|zip|bin)",
        private_name,
    ):
        raise ValueError("startup_source_ref_private_name_invalid")
    if not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ValueError("startup_source_ref_content_sha256_invalid")
    resolved_inbox_root = inbox_root.resolve()
    case_root = (resolved_inbox_root / str(case_id)).resolve()
    target = (case_root / private_name).resolve()
    if resolved_inbox_root != case_root and resolved_inbox_root not in case_root.parents:
        raise ValueError("startup_source_ref_private_name_invalid")
    if resolved_inbox_root != target and resolved_inbox_root not in target.parents:
        raise ValueError("startup_source_ref_private_name_invalid")
    if case_root != target.parent:
        raise ValueError("startup_source_ref_private_name_invalid")
    if not target.is_file():
        raise ValueError("startup_source_ref_not_found")
    if _hash_file(target) != content_hash:
        raise ValueError("startup_source_ref_content_sha256_mismatch")
    return content_hash, target


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _StartupPrivacyWorkflowPort:
    def __init__(
        self,
        privacy_service: StartupPrivacyService,
        *,
        parser: _StartupParsingWorkflowPort,
    ) -> None:
        self._privacy_service = privacy_service
        self._parser = parser

    def classify_redact(
        self,
        *,
        case_id: str,
        parsed_artifact_ids: list[str],
        data_revision: int = 1,
        raw_payload: str | None = None,
    ) -> dict[str, object]:
        del raw_payload
        blocks = self._parser.text_blocks(parsed_artifact_ids)
        if not blocks:
            return _fail_closed_disclosure_snapshot(
                case_id=case_id,
                parsed_artifact_ids=parsed_artifact_ids,
                policy_version=self._privacy_service.policy_version,
                reason="no_parsed_text_blocks",
                data_revision=data_revision,
            )
        try:
            redacted = self._privacy_service.redact_context(
                blocks,
                source_sensitivity=SensitivityClass.PUBLIC,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _fail_closed_disclosure_snapshot(
                case_id=case_id,
                parsed_artifact_ids=parsed_artifact_ids,
                policy_version=self._privacy_service.policy_version,
                reason=getattr(exc, "code", type(exc).__name__),
                data_revision=data_revision,
            )
        detected_classes = _startup_uploaded_document_detected_classes(redacted.sensitivity)
        snapshot = ClassifiedDisclosureSnapshot(
            case_id=UUID(case_id),
            detected_classes=detected_classes,
            overall_class=_most_restrictive_sensitivity(detected_classes),
            redaction_policy_version=self._privacy_service.policy_version,
            egress_policy_version=DataEgressPolicy.version,
            data_revision=data_revision,
            content_hash=redacted.content_hash,
            artifact_counts={"parsed": len(parsed_artifact_ids), "text_block": len(blocks)},
            mime_counts={},
            category_counts=dict(redacted.redaction_counts),
            redacted_fragment_ids=tuple(redacted.fragment_ids),
            minimized_fragment_refs=tuple(redacted.local_text_refs),
            destination="openai.responses",
        )
        return {
            "sensitivity_summary_id": f"summary-{redacted.content_hash[:16]}",
            "snapshot": snapshot,
        }


def _fail_closed_disclosure_snapshot(
    *,
    case_id: str,
    parsed_artifact_ids: list[str],
    policy_version: str,
    reason: str,
    data_revision: int = 1,
) -> dict[str, object]:
    content_hash = sha256(
        f"fail-closed:{case_id}:{'|'.join(parsed_artifact_ids)}".encode()
    ).hexdigest()
    fragment_id = uuid5(NAMESPACE_URL, f"startup-fail-closed:{content_hash}")
    snapshot = ClassifiedDisclosureSnapshot(
        case_id=UUID(case_id),
        detected_classes=frozenset({SensitivityClass.RESTRICTED}),
        overall_class=SensitivityClass.RESTRICTED,
        redaction_policy_version=policy_version,
        egress_policy_version=DataEgressPolicy.version,
        data_revision=data_revision,
        content_hash=content_hash,
        artifact_counts={"parsed": len(parsed_artifact_ids)},
        mime_counts={},
        category_counts={"restricted_source": max(1, len(parsed_artifact_ids))},
        redacted_fragment_ids=(fragment_id,),
        minimized_fragment_refs=(content_hash,),
        destination="openai.responses",
    )
    return {
        "sensitivity_summary_id": f"summary-{content_hash[:16]}",
        "snapshot": snapshot,
        "privacy_fail_closed_code": "startup_privacy_fail_closed",
        "privacy_fail_closed_reason": _safe_policy_reason(reason),
    }


def _safe_policy_reason(reason: str) -> str:
    safe = "".join(char if char.isalnum() or char in "_-" else "_" for char in reason)
    return safe[:80] or "unknown"


def _startup_uploaded_document_detected_classes(
    redacted_sensitivity: SensitivityClass,
) -> frozenset[SensitivityClass]:
    return frozenset({redacted_sensitivity, SensitivityClass.CONFIDENTIAL})


def _most_restrictive_sensitivity(classes: frozenset[SensitivityClass]) -> SensitivityClass:
    order = {
        SensitivityClass.PUBLIC: 0,
        SensitivityClass.INTERNAL: 1,
        SensitivityClass.CONFIDENTIAL: 2,
        SensitivityClass.RESTRICTED: 3,
    }
    return max(classes, key=lambda item: order[item])


class _StartupParsingWorkflowPort:
    def __init__(
        self,
        artifact_store: LocalArtifactStore,
        *,
        artifact_repository: LocalArtifactRepository,
        parsed_artifact_repository: LocalParsedStartupArtifactRepository,
        spreadsheet_parser: SpreadsheetParser | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._artifact_repository = artifact_repository
        self._parsed_artifact_repository = parsed_artifact_repository
        self._parser = StartupParsingService(
            artifact_store=artifact_store,
            spreadsheet_parser=spreadsheet_parser,
        )

    def parse(self, artifact: Any) -> ParsedStartupArtifact:
        parsed = self._parser.parse(artifact)
        self._parsed_artifact_repository.add(parsed)
        return parsed

    def documents(self, parsed_artifact_ids: list[str]) -> list[ParsedDocument]:
        documents: list[ParsedDocument] = []
        for artifact_id in parsed_artifact_ids:
            parsed = self._parsed_artifact(artifact_id)
            if parsed is None or parsed.document is None:
                continue
            documents.append(parsed.document)
        return documents

    def spreadsheets(self, parsed_artifact_ids: list[str]) -> list[ParsedStartupArtifact]:
        spreadsheets: list[ParsedStartupArtifact] = []
        for artifact_id in parsed_artifact_ids:
            parsed = self._parsed_artifact(artifact_id)
            if parsed is None or parsed.spreadsheet is None:
                continue
            spreadsheets.append(parsed)
        return spreadsheets

    def text_blocks_for_case(self, case_id: UUID) -> list[TextBlock]:
        parsed_ids = [
            str(parsed.artifact_id)
            for parsed in self._parsed_artifact_repository.list_for_case(case_id)
            if parsed.document is not None
        ]
        return self.text_blocks(parsed_ids)

    def text_blocks(self, parsed_artifact_ids: list[str]) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        for document in self.documents(parsed_artifact_ids):
            blocks.extend(document.text_blocks)
            for page in document.pages:
                blocks.extend(page.text_blocks)
            for table in document.tables:
                blocks.extend(table.text_blocks)
        unique: dict[str, TextBlock] = {}
        for block in blocks:
            if block.content_hash not in unique:
                unique[block.content_hash] = block
        return list(unique.values())

    def text_for_block(self, block: TextBlock) -> str:
        payload = self._artifact_store.read_bytes(block.text_ref)
        return payload.decode("utf-8", errors="replace")

    def _parsed_artifact(self, artifact_id: str) -> ParsedStartupArtifact | None:
        parsed_artifact_id = UUID(str(artifact_id))
        try:
            case_id = self._artifact_repository.case_id_for_artifact(parsed_artifact_id)
            return self._parsed_artifact_repository.get_for_case(case_id, parsed_artifact_id)
        except KeyError:
            return None


@dataclass(frozen=True)
class _ParsedArtifactRef:
    artifact_id: UUID


class _StartupEvidenceFromParsedDocumentsWorkflowPort:
    def __init__(
        self,
        evidence_repository: LocalEvidenceRepository,
        claim_repository: LocalStartupClaimRepository,
        *,
        parser: _StartupParsingWorkflowPort,
        contradiction_repository: LocalContradictionRepository,
    ) -> None:
        self._evidence_repository = evidence_repository
        self._claim_repository = claim_repository
        self._parser = parser
        self._claim_extractor = ClaimExtractionService()
        self._spreadsheet_scalar_extractor = StartupSpreadsheetScalarFactExtractor()
        self._explicit_contradiction_signals = ExplicitContradictionSignalService(
            contradiction_repository=contradiction_repository,
        )
        self._source_fact_contradictions = SourceFactContradictionService(
            contradiction_repository=contradiction_repository,
        )

    def extract(self, *, case_id: str, parsed_artifact_ids: list[str]) -> dict[str, Any]:
        fact_ids: list[str] = []
        claim_ids: list[str] = []
        case_uuid = UUID(case_id)
        for parsed in self._parser.spreadsheets(parsed_artifact_ids):
            spreadsheet = parsed.spreadsheet
            if spreadsheet is None:
                continue
            for fact in spreadsheet.evidence_facts:
                try:
                    self._evidence_repository.add(fact)
                except ValueError as exc:
                    if str(exc) != "evidence_fact_already_exists":
                        raise
                fact_ids.append(str(fact.id))
            if isinstance(parsed, ParsedStartupArtifact):
                scalar_facts = self._spreadsheet_scalar_extractor.extract(
                    parsed,
                    sensitivity=SensitivityClass.CONFIDENTIAL,
                    existing_facts=self._evidence_repository.list_for_case(case_uuid),
                )
                for fact in scalar_facts:
                    try:
                        self._evidence_repository.add(fact)
                    except ValueError as exc:
                        if str(exc) != "evidence_fact_already_exists":
                            raise
                    fact_ids.append(str(fact.id))
        explicit_contradiction_ids: list[str] = []
        for index, block in enumerate(self._parser.text_blocks(parsed_artifact_ids), start=1):
            artifact_id = block.locator.artifact_id
            if artifact_id is None:
                continue
            text = self._parser.text_for_block(block)
            is_founder_clarification = is_founder_clarification_text(text)
            claim_text = (
                without_founder_clarification_marker(text) if is_founder_clarification else text
            )
            text_fact = _text_block_evidence_fact(case_uuid, block, source_priority=index)
            try:
                self._evidence_repository.add(text_fact)
            except ValueError as exc:
                if str(exc) != "evidence_fact_already_exists":
                    raise
            fact_ids.append(str(text_fact.id))
            explicit_contradictions = self._explicit_contradiction_signals.materialize_from_text(
                case_id=case_uuid,
                text_fact=text_fact,
                text=claim_text,
            )
            explicit_contradiction_ids.extend(str(item.id) for item in explicit_contradictions)
            claims = self._claim_extractor.extract_fixture_claims(
                case_id=case_uuid,
                artifact_id=artifact_id,
                text=claim_text,
                locator=block.locator,
                sensitivity=SensitivityClass.CONFIDENTIAL,
                period="unknown",
            )
            for claim in claims:
                stable_claim = _stable_startup_claim(case_uuid, claim)
                try:
                    self._claim_repository.add(stable_claim)
                except ValueError as exc:
                    if str(exc) != "startup_claim_already_exists":
                        raise
                claim_ids.append(str(stable_claim.id))
                if stable_claim.normalized_value is None:
                    continue
                fact = _evidence_fact_from_startup_claim(
                    stable_claim,
                    source_priority=(
                        SourcePriority.MANAGEMENT_NARRATIVE if is_founder_clarification else index
                    ),
                    founder_clarification=is_founder_clarification,
                )
                try:
                    self._evidence_repository.add(fact)
                except ValueError as exc:
                    if str(exc) != "evidence_fact_already_exists":
                        raise
                fact_ids.append(str(fact.id))
        contradictions = self._source_fact_contradictions.materialize(
            case_id=case_uuid,
            evidence_facts=self._evidence_repository.list_for_case(case_uuid),
        )
        return {
            "evidence_fact_ids": list(dict.fromkeys(fact_ids)),
            "startup_claim_ids": list(dict.fromkeys(claim_ids)),
            "contradiction_ids": list(
                dict.fromkeys(
                    [*explicit_contradiction_ids, *[str(item.id) for item in contradictions]]
                )
            ),
        }


class _StartupProviderWorkflowPort:
    def __init__(self, *, provider: Any | None, finding_repository: LocalFindingRepository) -> None:
        self._provider = provider
        self._finding_repository = finding_repository
        self.trace_tool_name = _startup_provider_trace_tool_name(provider)

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> StartupProviderAnalysisResult:
        if self._provider is None:
            raise StartupProviderConfigurationError()
        result = self._provider.analyze(
            case_id=case_id,
            node_name=node_name,
            disclosure_scope=disclosure_scope,
            remaining_evidence_fact_ids=remaining_evidence_fact_ids,
            remaining_calculation_ids=remaining_calculation_ids,
            invalidated_ids=invalidated_ids,
        )
        if not isinstance(result, dict):
            raise StartupProviderConfigurationError("startup_provider_invalid_result")
        finding_ids = []
        for item in result.get("finding_ids", []):
            finding_id = str(item)
            if not self._finding_exists(finding_id):
                raise StartupProviderConfigurationError("startup_provider_unpersisted_finding_id")
            finding_ids.append(finding_id)
        for finding in result.get("findings", []):
            if not isinstance(finding, Finding):
                raise StartupProviderConfigurationError("startup_provider_invalid_finding")
            try:
                self._finding_repository.add(finding)
            except ValueError as exc:
                if str(exc) != "finding_already_exists":
                    raise
            finding_ids.append(str(finding.id))
        return {"finding_ids": list(dict.fromkeys(finding_ids))}

    def _finding_exists(self, finding_id: str) -> bool:
        try:
            UUID(finding_id)
        except ValueError as exc:
            raise StartupProviderConfigurationError("startup_provider_invalid_finding_id") from exc
        database = getattr(self._finding_repository, "_db", None)
        if database is None:
            return False
        row = database.fetch_one("SELECT id FROM findings WHERE id = ?", (finding_id,))
        return row is not None


class StartupProviderConfigurationError(RuntimeError):
    retryable = False

    def __init__(self, code: str = "startup_provider_not_configured") -> None:
        super().__init__(code)
        self.code = code


def _startup_provider_trace_tool_name(provider: Any | None) -> str | None:
    if provider is None:
        return None
    explicit = getattr(provider, "trace_tool_name", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    return type(provider).__name__


class _DeterministicStartupProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.external_calls: list[str] = []

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        del (
            case_id,
            disclosure_scope,
            remaining_evidence_fact_ids,
            remaining_calculation_ids,
            invalidated_ids,
        )
        self.calls.append(node_name)
        return {"finding_ids": []}


def _stable_startup_claim(case_id: UUID, claim: StartupClaim) -> StartupClaim:
    material = "|".join(
        (
            str(case_id),
            str(claim.source_artifact_id),
            claim.text_hash,
            claim.category.value,
            claim.normalized_name,
            str(claim.normalized_value),
            str(claim.unit),
            str(claim.period),
        )
    )
    return claim.model_copy(update={"id": uuid5(NAMESPACE_URL, f"startup-claim:{material}")})


def _evidence_fact_from_startup_claim(
    claim: StartupClaim,
    *,
    source_priority: int,
    founder_clarification: bool = False,
) -> EvidenceFact:
    value = claim.normalized_value
    if value is None:
        raise ValueError("startup_numeric_claim_missing_value")
    return EvidenceFact(
        id=uuid5(NAMESPACE_URL, f"startup-claim-fact:{claim.id}"),
        artifact_id=claim.source_artifact_id,
        name=claim.normalized_name,
        value=value,
        value_type="decimal",
        unit=claim.unit,
        period=claim.period,
        locator=claim.locator,
        sensitivity=claim.sensitivity,
        confidence=(
            max(claim.confidence, Decimal("0.95")) if founder_clarification else claim.confidence
        ),
        source_priority=source_priority,
        extraction_method=(
            "founder_clarification" if founder_clarification else "startup-structured-claim@1"
        ),
        supporting_text_hash=claim.text_hash,
        source_freshness_at=claim.extracted_at,
        retrieved_at=claim.extracted_at,
        metadata={
            "parser_boundary": "startup_parsed_document",
            "startup_claim_id": str(claim.id),
            "claim_category": claim.category.value,
            **({"founder_clarification": "accepted_source"} if founder_clarification else {}),
        },
    )


def _text_block_evidence_fact(
    case_id: UUID,
    block: TextBlock,
    *,
    source_priority: int,
) -> EvidenceFact:
    if block.locator.artifact_id is None:
        raise ValueError("startup_text_block_missing_artifact_id")
    now = datetime.now(UTC)
    return EvidenceFact(
        id=uuid5(
            NAMESPACE_URL,
            f"startup-evidence:{case_id}:{block.locator.artifact_id}:{block.content_hash}",
        ),
        artifact_id=block.locator.artifact_id,
        name=f"document_text_block_{source_priority:03d}",
        value=f"text_block:{block.content_hash[:16]}",
        value_type="text",
        unit=None,
        period=None,
        locator=block.locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=block.confidence,
        source_priority=source_priority,
        extraction_method="startup-parsed-document@1",
        supporting_text_hash=block.content_hash,
        source_freshness_at=now,
        retrieved_at=now,
        metadata={
            "parser_boundary": "startup_parsed_document",
            "text_hash": block.content_hash,
        },
    )


def _startup_case(case_id: UUID) -> DueDiligenceCase:
    now = datetime.now(UTC)
    return DueDiligenceCase(
        case_id=case_id,
        mode=AnalysisMode.STARTUP,
        entity_name="Startup data room",
        entity_identifier=str(case_id),
        jurisdiction="local",
        scope=("uploaded_data_room",),
        period_start=None,
        period_end=None,
        as_of=now,
        base_currency="USD",
        privacy_policy="startup-local@1",
        budget_policy="startup-local@1",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=now,
        updated_at=now,
        workflow_version="startup-task9@1",
    )


def build_fixture_sources(fixture_root: Path) -> PublicSources:
    return PublicSources(
        sec=FixtureSecSource(fixture_root / "sec"),
        market=YFinanceDemoAdapter.from_fixture_dir(fixture_root / "market"),
        news=GdeltNewsAdapter.from_fixture_dir(fixture_root / "news"),
    )


def public_us_frozen_fixture_root(stack: ExitStack) -> Path:
    package_root = resources.files("due_diligence_agent").joinpath(
        "fixtures", PUBLIC_US_FROZEN_FIXTURE_NAME
    )
    if package_root.is_dir():
        return stack.enter_context(resources.as_file(package_root))
    fallback_root = _project_root() / "tests" / "fixtures" / PUBLIC_US_FROZEN_FIXTURE_NAME
    if fallback_root.is_dir():
        return fallback_root
    raise FileNotFoundError(
        f"{PUBLIC_US_FROZEN_FIXTURE_NAME} fixture not found in package resources or tests/fixtures"
    )


def startup_market_fixture_root() -> Path | Traversable:
    package_root = resources.files("due_diligence_agent").joinpath(
        "fixtures", STARTUP_MARKET_FIXTURE_NAME
    )
    if package_root.is_dir():
        return package_root
    fallback_root = _project_root() / "tests" / "fixtures" / STARTUP_MARKET_FIXTURE_NAME
    if fallback_root.is_dir():
        return fallback_root
    raise FileNotFoundError(
        f"{STARTUP_MARKET_FIXTURE_NAME} fixture not found in package resources or tests/fixtures"
    )


def public_us_frozen_fixture_manifest() -> dict[str, Any]:
    package_manifest = resources.files("due_diligence_agent").joinpath(
        "fixtures", PUBLIC_US_FROZEN_FIXTURE_NAME, "manifest.json"
    )
    if package_manifest.is_file():
        return cast(dict[str, Any], json.loads(package_manifest.read_text(encoding="utf-8")))
    fallback_manifest = (
        _project_root() / "tests" / "fixtures" / PUBLIC_US_FROZEN_FIXTURE_NAME / "manifest.json"
    )
    return _load_json(fallback_manifest)


def build_live_sources(settings: Settings) -> PublicSources:
    cache = SnapshotCache(settings.data_dir / "source-cache" / "sec")
    sec = SecEdgarAdapter(
        user_agent=settings.sec_user_agent,
        cache=cache,
        limiter=FairAccessLimiter(max_requests_per_second=settings.sec_max_requests_per_second),
    )
    return PublicSources(sec=sec, market=YFinanceDemoAdapter(), news=GdeltNewsAdapter())


def build_retrieval_service(
    *,
    settings: Settings,
    artifact_store: LocalArtifactStore,
    use_fixture_adapters: bool,
) -> RetrievalService:
    embedding = (
        DeterministicFixtureEmbeddingAdapter()
        if use_fixture_adapters
        else LocalEmbeddingAdapter(_resolve_embedding_model_dir(settings))
    )
    index = FaissEvidenceIndex(
        root=settings.data_dir / "retrieval-index",
        embedding=embedding,
        artifact_store=artifact_store,
    )
    return RetrievalService(
        artifact_store=artifact_store,
        parser=FilingParsingService(),
        index=index,
    )


def _resolve_embedding_model_dir(settings: Settings) -> Path:
    if settings.embedding_model_dir.is_absolute():
        return settings.embedding_model_dir
    return settings.data_dir / settings.embedding_model_dir


class FixtureSecSource:
    provider = "sec"
    provider_version = "fixture@1"
    license_class = "public_primary"

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir.resolve()
        self._manifest = _load_json(self.fixture_dir / "manifest.json")

    async def resolve_company(self, ticker_or_cik: str, *, as_of: date) -> CompanyIdentity:
        del as_of
        requested = ticker_or_cik.strip().upper()
        tickers = _load_json(self.fixture_dir / "company_tickers.json")
        for entry in tickers.values():
            if str(entry["ticker"]).strip().upper() == requested:
                return CompanyIdentity(
                    cik=str(entry["cik_str"]).zfill(10),
                    ticker=requested,
                    name=str(entry["title"]),
                    snapshot=self._snapshot("company_tickers.json", query={"ticker": requested}),
                )
        raise ValueError(f"ticker_not_found:{ticker_or_cik}")

    async def list_submissions(self, cik: str, *, as_of: date) -> SubmissionsSnapshot:
        normalized = cik.zfill(10)
        name = "submissions.json" if normalized == "0000320193" else "brk-submissions.json"
        data = _load_json(self.fixture_dir / name)
        return SubmissionsSnapshot(
            data=data,
            snapshot=self._snapshot(name, query={"cik": normalized}, as_of=as_of),
        )

    async def get_company_facts(self, cik: str, *, as_of: date) -> CompanyFactsSnapshot:
        data = _load_json(self.fixture_dir / "companyfacts.json")
        return CompanyFactsSnapshot(
            data=data,
            snapshot=self._snapshot("companyfacts.json", query={"cik": cik.zfill(10)}, as_of=as_of),
        )

    async def fetch_filing(
        self, accession_number: str, *, as_of: date
    ) -> NodeResult[FilingArtifact]:
        for name, entry in cast(dict[str, Any], self._manifest["files"]).items():
            if entry.get("accession_number") == accession_number and name.endswith(".html"):
                path = self._safe_path(name)
                snapshot = self._snapshot(
                    name, query={"accession_number": accession_number}, as_of=as_of
                )
                return NodeResult(
                    status=NodeStatus.SUCCESS,
                    data=FilingArtifact(
                        accession_number=accession_number,
                        content=path.read_bytes(),
                        snapshot=snapshot,
                    ),
                )
        return NodeResult(
            status=NodeStatus.BLOCKED,
            errors=[f"primary_filing_not_found:{accession_number}"],
        )

    def _snapshot(
        self, name: str, *, query: dict[str, str], as_of: date | None = None
    ) -> SourceSnapshot:
        path = self._safe_path(name)
        entry = cast(dict[str, Any], self._manifest["files"][name])
        payload = path.read_bytes()
        digest = sha256(payload).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"fixture hash mismatch:{name}")
        retrieved = _parse_utc(str(self._manifest["retrieved_at"]))
        published = _parse_optional_utc(entry.get("filing_acceptance_at"))
        return SourceSnapshot(
            provider=self.provider,
            provider_version=self.provider_version,
            source_url=str(entry["retrieval_url"]),
            query=query,
            as_of=as_of or date.fromisoformat(str(self._manifest["as_of"])),
            retrieved_at=retrieved,
            published_at=published,
            content_hash=digest,
            license_class=str(entry["license_class"]),
            media_type="text/html" if name.endswith(".html") else "application/json",
            storage_ref=path.name,
        )

    def _safe_path(self, name: str) -> Path:
        path = (self.fixture_dir / name).resolve()
        if self.fixture_dir not in path.parents:
            raise ValueError("fixture path escapes root")
        return path


class LocalAuditRecorder:
    def __init__(
        self, spool: JsonlAuditSpool, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._spool = spool
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(self, node_name: str, result: NodeResult[Any], state: dict[str, Any]) -> None:
        case_id = str(state.get("case_id") or "case-unknown")
        event = AuditEvent(
            schema_version="audit_event@1",
            event_id=str(uuid4()),
            timestamp_utc=self._clock().isoformat().replace("+00:00", "Z"),
            run_id=_safe_run_id(case_id),
            correlation_id=_safe_run_id(case_id),
            span_name="analysis.module",
            event_type="span",
            attributes={
                "node_name": node_name,
                "status": result.status.value,
                "case_id": case_id,
                "evidence_count": len(result.data_refs),
                "chunk_count": len(result.warnings),
                "retry_count": len(result.errors),
            },
        )
        self._spool.append(event)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _parse_optional_utc(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_utc(str(value))


def _safe_run_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "_.-" else "-" for char in value)
    return (safe.strip(".-") or "local-run")[:120]


def _close_public_sources(sources: PublicSources) -> None:
    for source in (sources.sec, sources.market, sources.news):
        client = getattr(source, "client", None)
        if client is not None:
            _close_client(client)


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()
        return
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        result = aclose()
        if inspect.isawaitable(result):
            with asyncio.Runner() as runner:
                runner.run(_await_client_close(result))


async def _await_client_close(awaitable: Any) -> None:
    await awaitable


async def _no_async_sleep(_seconds: float) -> None:
    return None
