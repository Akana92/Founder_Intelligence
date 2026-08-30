from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from fastapi import Request

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.product.capabilities import ProductCapabilitiesService
from due_diligence_agent.application.services.case_asset_service import CaseAssetService
from due_diligence_agent.application.services.case_copilot_service import CaseCopilotService
from due_diligence_agent.application.services.startup_advisor_api_service import (
    StartupAdvisorApiService,
)
from due_diligence_agent.application.startup_advisor_recalculation import (
    StartupAdvisorCaseRecalculationAdapter,
)
from due_diligence_agent.application.startup_cases import StartupCaseCoordinator
from due_diligence_agent.config import OpenAIStartupSettings, Settings
from due_diligence_agent.presentation.api.context import RequestContext
from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore

if TYPE_CHECKING:
    from due_diligence_agent.bootstrap.container import LocalRepositories, OpenAIStartupAIComponents


class _FixtureAwareCaseService:
    """Route one case-local API call to the data root selected at case creation."""

    def __init__(
        self,
        *,
        workflow_store: SQLiteStartupWorkflowRuntimeStore,
        live_service: Any,
        deterministic_service: Any,
    ) -> None:
        self._workflow_store = workflow_store
        self._live_service = live_service
        self._deterministic_service = deterministic_service

    def __getattr__(self, name: str) -> Any:
        live_member = getattr(self._live_service, name)
        if not callable(live_member):
            return live_member

        def routed(case_id: UUID, *args: Any, **kwargs: Any) -> Any:
            service = self._service_for_case(case_id)
            return getattr(service, name)(case_id, *args, **kwargs)

        return routed

    def _service_for_case(self, case_id: UUID) -> Any:
        runtime = self._workflow_store.load(str(case_id))
        if runtime.get("fixture_mode") == "deterministic_offline":
            return self._deterministic_service
        return self._live_service


def get_product_capabilities_service() -> ProductCapabilitiesService:
    return ProductCapabilitiesService()


@lru_cache(maxsize=1)
def get_case_copilot_service() -> CaseCopilotService:
    from due_diligence_agent.bootstrap import container

    _disable_automatic_langsmith_tracing()
    settings = Settings()
    openai_settings = OpenAIStartupSettings()
    data_dir = settings.data_dir / "startup-api"
    deterministic_data_dir = data_dir / "deterministic"
    workflow_store = SQLiteStartupWorkflowRuntimeStore(
        data_dir / "startup-runtime.sqlite3"
    )
    analysis_revision_starter = get_startup_case_coordinator().seed_revision_analysis
    live_research_port = None
    if openai_settings.openai_api_key is not None:
        repositories = container.build_local_repositories(
            data_dir / "startup-metadata.sqlite3"
        )
        live_research_port = container.build_openai_startup_research_port(
            settings=openai_settings,
            repositories=repositories,
            audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
            llm_call_recorder=_build_public_research_llm_call_recorder(
                settings=settings,
                data_dir=data_dir,
            ),
        )
    live_service = container.build_case_copilot_service(
        data_dir=data_dir,
        workflow_store=workflow_store,
        inbox_root=data_dir / "inbox",
        live_research_port=live_research_port,
        analysis_revision_starter=analysis_revision_starter,
    )
    deterministic_service = container.build_case_copilot_service(
        data_dir=deterministic_data_dir,
        workflow_store=workflow_store,
        inbox_root=data_dir / "inbox",
        research_provider=container.DeterministicCaseCopilotBenchmarkProvider(),
        acquisition_mode="deterministic_offline_fixture",
        analysis_revision_starter=analysis_revision_starter,
    )
    return cast(
        CaseCopilotService,
        _FixtureAwareCaseService(
            workflow_store=workflow_store,
            live_service=live_service,
            deterministic_service=deterministic_service,
        ),
    )


@lru_cache(maxsize=1)
def get_case_asset_service() -> CaseAssetService:
    from due_diligence_agent.bootstrap import container

    settings = Settings()
    data_dir = settings.data_dir / "startup-api"
    workflow_store = SQLiteStartupWorkflowRuntimeStore(
        data_dir / "startup-runtime.sqlite3"
    )
    return cast(
        CaseAssetService,
        _FixtureAwareCaseService(
            workflow_store=workflow_store,
            live_service=container.build_case_asset_service(data_dir=data_dir),
            deterministic_service=container.build_case_asset_service(
                data_dir=data_dir / "deterministic"
            ),
        ),
    )


@lru_cache(maxsize=1)
def get_startup_advisor_api_service() -> StartupAdvisorApiService:
    from due_diligence_agent.bootstrap import container

    _disable_automatic_langsmith_tracing()
    settings = Settings()
    openai_settings = OpenAIStartupSettings()
    data_dir = settings.data_dir / "startup-api"
    deterministic_data_dir = data_dir / "deterministic"
    workflow_store = SQLiteStartupWorkflowRuntimeStore(
        data_dir / "startup-runtime.sqlite3"
    )
    return container.build_startup_advisor_api_service(
        data_dir=data_dir,
        deterministic_data_dir=deterministic_data_dir,
        workflow_store=workflow_store,
        recalculation_port=StartupAdvisorCaseRecalculationAdapter(
            coordinator=get_startup_case_coordinator(),
            workflow_store=workflow_store,
            founder_statement_intake=container.build_case_fact_intake_service(data_dir),
            deterministic_founder_statement_intake=container.build_case_fact_intake_service(
                deterministic_data_dir
            ),
            profile_repository=container.build_startup_profile_query_port(data_dir),
            deterministic_profile_repository=container.build_startup_profile_query_port(
                deterministic_data_dir
            ),
        ),
        openai_settings=openai_settings,
        llm_call_recorder=(
            _build_public_research_llm_call_recorder(
                settings=settings,
                data_dir=data_dir,
            )
            if openai_settings.openai_api_key is not None
            else None
        ),
    )


@lru_cache(maxsize=1)
def get_startup_case_coordinator() -> StartupCaseCoordinator:
    from due_diligence_agent.bootstrap import container

    _disable_automatic_langsmith_tracing()
    settings = Settings()
    openai_settings = OpenAIStartupSettings()
    data_dir = settings.data_dir / "startup-api"
    deterministic_data_dir = data_dir / "deterministic"
    inbox_root = data_dir / "inbox"
    runtime_path = data_dir / "startup-runtime.sqlite3"
    from due_diligence_agent.adapters.observability.startup_langsmith import (
        StartupLangSmithNodeTracer,
        StartupLangSmithTracerConfig,
    )

    external_node_tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(
            enabled=bool(getattr(settings, "langsmith_tracing", False)),
            credential_present=bool(
                os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
            ),
        ),
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
    )
    ai_components_factory = None
    live_provider_configured = openai_settings.openai_api_key is not None
    if live_provider_configured:

        def ai_components_factory(
            repositories: LocalRepositories,
            audit_spool: JsonlAuditSpool,
        ) -> OpenAIStartupAIComponents | None:
            return container.build_openai_startup_components(
                settings=openai_settings,
                repositories=repositories,
                audit_spool=audit_spool,
                llm_call_recorder=external_node_tracer.record,
            )
    deterministic_node_tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(enabled=False, credential_present=False),
        audit_spool=JsonlAuditSpool(deterministic_data_dir / "startup-audit-spool"),
    )
    if ai_components_factory is not None and external_node_tracer is not None:
        analysis_service = container.build_startup_analysis_composer(
            data_dir,
            ai_components_factory=ai_components_factory,
            external_node_tracer=external_node_tracer,
        )
    elif ai_components_factory is not None:
        analysis_service = container.build_startup_analysis_composer(
            data_dir,
            ai_components_factory=ai_components_factory,
        )
    elif external_node_tracer is not None:
        analysis_service = container.build_startup_analysis_composer(
            data_dir,
            external_node_tracer=external_node_tracer,
        )
    else:
        analysis_service = container.build_startup_analysis_composer(data_dir)
    revision_port_factory = getattr(container, "build_startup_case_revision_port", None)
    case_revision_port = (
        revision_port_factory(data_dir) if callable(revision_port_factory) else None
    )
    deterministic_case_revision_port = (
        revision_port_factory(deterministic_data_dir)
        if callable(revision_port_factory)
        else None
    )
    profile_port_factory = getattr(container, "build_startup_profile_query_port", None)
    profile_port = profile_port_factory(data_dir) if callable(profile_port_factory) else None
    deterministic_profile_port = (
        profile_port_factory(deterministic_data_dir)
        if callable(profile_port_factory)
        else None
    )
    gtm_port_factory = getattr(container, "build_startup_gtm_query_port", None)
    gtm_port = gtm_port_factory(data_dir) if callable(gtm_port_factory) else None
    deterministic_gtm_port = (
        gtm_port_factory(deterministic_data_dir)
        if callable(gtm_port_factory)
        else None
    )
    return StartupCaseCoordinator(
        analysis_service=analysis_service,
        deterministic_analysis_service=container.build_deterministic_startup_analysis_composer(
            deterministic_data_dir,
            inbox_root=inbox_root,
            external_node_tracer=deterministic_node_tracer,
        ),
        report_port=container.build_startup_report_port(data_dir),
        deterministic_report_port=container.build_startup_report_port(deterministic_data_dir),
        profile_port=profile_port,
        deterministic_profile_port=deterministic_profile_port,
        gtm_port=gtm_port,
        deterministic_gtm_port=deterministic_gtm_port,
        case_revision_port=case_revision_port,
        deterministic_case_revision_port=deterministic_case_revision_port,
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
        deterministic_audit_spool=JsonlAuditSpool(
            deterministic_data_dir / "startup-audit-spool"
        ),
        workflow_store=SQLiteStartupWorkflowRuntimeStore(runtime_path),
        inbox_root=inbox_root,
        live_provider_configured=live_provider_configured,
    )


def get_request_context(request: Request) -> RequestContext:
    context = request.state.request_context
    if not isinstance(context, RequestContext):
        raise RuntimeError("request_context.missing")  # noqa: TRY004
    return context


def _disable_automatic_langsmith_tracing() -> None:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


def _build_public_research_llm_call_recorder(
    *,
    settings: Settings,
    data_dir: Path,
) -> Callable[..., None]:
    from due_diligence_agent.adapters.observability.startup_langsmith import (
        StartupLangSmithNodeTracer,
        StartupLangSmithTracerConfig,
    )

    tracer = StartupLangSmithNodeTracer(
        StartupLangSmithTracerConfig(
            enabled=bool(getattr(settings, "langsmith_tracing", False)),
            credential_present=bool(
                os.environ.get("LANGSMITH_API_KEY")
                or os.environ.get("LANGCHAIN_API_KEY")
            ),
        ),
        audit_spool=JsonlAuditSpool(data_dir / "startup-audit-spool"),
    )

    def record_public_research_llm_call(**attributes: object | None) -> None:
        tracer.record(**attributes)
        tracer.flush()

    return record_public_research_llm_call
