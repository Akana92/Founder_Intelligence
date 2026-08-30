from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import JSONResponse, PlainTextResponse

from due_diligence_agent.application.case_copilot_contracts import (
    AssumptionOutcomeResponse,
    CaseAssetListResponse,
    CaseAssetResponse,
    CopilotStateResponse,
    CopilotThreadResponse,
    CopilotTurnResponse,
    FactMutationResponse,
    GenerateCaseAssetRequest,
    PostCopilotMessageRequest,
    PrepareResearchPlanRequest,
    QueueResearchJobRequest,
    ResearchJobResponse,
    ResearchPlanResponse,
    SaveAssumptionRequest,
    SaveFounderFactRequest,
    ScenarioProjectionResponse,
    ScenarioSelectionResponse,
    SelectScenarioRequest,
)
from due_diligence_agent.application.services.case_copilot_service import (
    CaseCopilotService,
    _FactValidationFailure,
)
from due_diligence_agent.application.services.case_asset_service import CaseAssetService
from due_diligence_agent.application.startup_cases import StartupValidationError
from due_diligence_agent.domain.startup.assets import CaseAssetDraft
from due_diligence_agent.presentation.api.dependencies import (
    get_case_asset_service,
    get_case_copilot_service,
)


router = APIRouter(prefix="/api/v1/startup", tags=["startup-copilot"])


@router.get("/cases/{case_id}/copilot/state", response_model=CopilotStateResponse)
def get_copilot_state(
    case_id: UUID,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> CopilotStateResponse:
    return service.state(case_id)


@router.get("/cases/{case_id}/copilot/thread", response_model=CopilotThreadResponse)
def get_copilot_thread(
    case_id: UUID,
    thread_id: UUID | None = Query(default=None),
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> CopilotThreadResponse:
    return service.thread(case_id, thread_id=thread_id)


@router.post("/cases/{case_id}/copilot/messages", response_model=CopilotTurnResponse)
def post_copilot_message(
    case_id: UUID,
    request: PostCopilotMessageRequest,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> CopilotTurnResponse:
    return service.post_message(case_id, request)


@router.post("/cases/{case_id}/facts", response_model=FactMutationResponse)
def save_fact(
    case_id: UUID,
    request: SaveFounderFactRequest,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> FactMutationResponse | JSONResponse:
    try:
        return service.save_fact(case_id, request)
    except _FactValidationFailure as exc:
        return JSONResponse(
            status_code=422,
            content={
                "code": "fact_validation_failed",
                "message": "fact_validation_failed",
                "errors": [item.model_dump(mode="json") for item in exc.errors],
            },
        )


@router.post("/cases/{case_id}/assumptions", response_model=AssumptionOutcomeResponse)
def save_assumption(
    case_id: UUID,
    request: SaveAssumptionRequest,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> AssumptionOutcomeResponse:
    return service.save_assumption(case_id, request)


@router.get("/cases/{case_id}/scenarios", response_model=ScenarioProjectionResponse)
def get_scenarios(
    case_id: UUID,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> ScenarioProjectionResponse:
    return service.scenarios(case_id)


@router.post(
    "/cases/{case_id}/scenarios/selection",
    response_model=ScenarioSelectionResponse,
)
def select_scenario(
    case_id: UUID,
    request: SelectScenarioRequest,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> ScenarioSelectionResponse:
    return service.select_scenario(case_id, request)


@router.post(
    "/cases/{case_id}/research/plans",
    response_model=ResearchPlanResponse,
    status_code=201,
)
def prepare_research_plan(
    case_id: UUID,
    request: PrepareResearchPlanRequest,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> ResearchPlanResponse:
    return service.prepare_research_plan(case_id, request)


@router.post(
    "/cases/{case_id}/research/jobs",
    response_model=ResearchJobResponse,
    status_code=202,
)
def queue_research_job(
    case_id: UUID,
    request: QueueResearchJobRequest,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> ResearchJobResponse:
    if request.acquisition_mode is None:
        raise StartupValidationError("research_acquisition_mode_required")
    return service.queue_research_job(case_id, request)


@router.get(
    "/cases/{case_id}/research/jobs/{job_id}",
    response_model=ResearchJobResponse,
)
def get_research_job(
    case_id: UUID,
    job_id: UUID,
    service: CaseCopilotService = Depends(get_case_copilot_service),
) -> ResearchJobResponse:
    return service.research_job(case_id, job_id)


@router.get("/cases/{case_id}/assets", response_model=CaseAssetListResponse)
def list_case_assets(
    case_id: UUID,
    service: CaseAssetService = Depends(get_case_asset_service),
) -> CaseAssetListResponse:
    return CaseAssetListResponse(
        case_id=case_id,
        data_revision=service.data_revision(case_id),
        assets=tuple(_asset_response(case_id, draft) for draft in service.list(case_id)),
    )


@router.post("/cases/{case_id}/assets", response_model=CaseAssetResponse, status_code=201)
def generate_case_asset(
    case_id: UUID,
    request: GenerateCaseAssetRequest,
    service: CaseAssetService = Depends(get_case_asset_service),
) -> CaseAssetResponse:
    draft = service.generate(
        case_id,
        asset_type=request.asset_type,
        selected_scenario_key=request.selected_scenario_key,
        expected_case_revision=request.expected_case_revision,
        idempotency_key=request.idempotency_key,
    )
    return _asset_response(case_id, draft)


@router.get("/cases/{case_id}/assets/{asset_id}", response_model=CaseAssetResponse)
def get_case_asset(
    case_id: UUID,
    asset_id: UUID,
    service: CaseAssetService = Depends(get_case_asset_service),
) -> CaseAssetResponse:
    return _asset_response(case_id, service.get(case_id, asset_id))


@router.get("/cases/{case_id}/assets/{asset_id}/markdown", response_class=PlainTextResponse)
def get_case_asset_markdown(
    case_id: UUID,
    asset_id: UUID,
    service: CaseAssetService = Depends(get_case_asset_service),
) -> PlainTextResponse:
    draft = service.get(case_id, asset_id)
    return PlainTextResponse(
        draft.body_markdown,
        headers={"Content-Disposition": _attachment_name(draft, "md")},
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/cases/{case_id}/assets/{asset_id}/provenance", response_class=PlainTextResponse)
def get_case_asset_provenance(
    case_id: UUID,
    asset_id: UUID,
    service: CaseAssetService = Depends(get_case_asset_service),
) -> PlainTextResponse:
    draft = service.get(case_id, asset_id)
    return PlainTextResponse(
        service.provenance_appendix(case_id, asset_id),
        headers={"Content-Disposition": _attachment_name(draft, "provenance.md")},
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/cases/{case_id}/assets/{asset_id}/csv", response_class=PlainTextResponse)
def get_case_asset_csv(
    case_id: UUID,
    asset_id: UUID,
    service: CaseAssetService = Depends(get_case_asset_service),
) -> PlainTextResponse:
    csv = service.csv_content(case_id, asset_id)
    if csv is None:
        raise HTTPException(status_code=404, detail={"code": "asset_csv_not_supported"})
    draft = service.get(case_id, asset_id)
    return PlainTextResponse(
        csv,
        headers={"Content-Disposition": _attachment_name(draft, "csv")},
        media_type="text/csv; charset=utf-8",
    )


def _asset_response(case_id: UUID, draft: CaseAssetDraft) -> CaseAssetResponse:
    base = f"/api/startup/cases/{case_id}/assets/{draft.draft_id}"
    return CaseAssetResponse(
        case_id=draft.case_id,
        data_revision=draft.data_revision,
        scenario_set_id=draft.scenario_set_id,
        selected_scenario_key=draft.selected_scenario_key,
        asset_id=draft.draft_id,
        asset_key=draft.asset_key,
        asset_revision=draft.draft_version,
        status=draft.status,
        markdown_url=f"{base}/markdown",
        csv_url=f"{base}/csv" if draft.asset_key == "weekly_funnel_template" else None,
        provenance_appendix_url=f"{base}/provenance",
        body_markdown=draft.body_markdown,
    )


def _attachment_name(draft: CaseAssetDraft, extension: str) -> str:
    safe_key = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in draft.asset_key)
    return f'attachment; filename="{safe_key}-{draft.draft_id}.{extension}"'


__all__ = ["router"]
