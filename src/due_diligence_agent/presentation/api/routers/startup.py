from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from starlette.responses import JSONResponse

from due_diligence_agent.application.startup_cases import (
    StartupCaseCoordinator,
    StartupCaseResponse,
    StartupDecisionResponse,
    StartupError,
    StartupGate2PreviewResponse,
    StartupGtmResponse,
    StartupProfileResponse,
    StartupReportResponse,
    StartupStatusResponse,
    StartupUploadResponse,
)
from due_diligence_agent.application.services.startup_advisor_api_service import (
    AdvisorAnswerResponse,
    AdvisorNextQuestionResponse,
    StartupAdvisorApiService,
    StartupImprovementDecisionResponse,
    StartupImprovementsResponse,
)
from due_diligence_agent.presentation.api.dependencies import (
    get_startup_advisor_api_service,
    get_startup_case_coordinator,
)

router = APIRouter(prefix="/api/v1/startup", tags=["startup"])


class StartupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_mode: Literal["live", "deterministic_offline"]
    auto_start: bool = True
    company_name: str | None = None
    website: str | None = None
    as_of: str | None = None
    document_class_hint: str | None = None


class Gate2DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "denied"]
    resume_token: str
    reason: str | None = None


class Gate3ExclusionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_fact_id: str
    reason: str | None = None


class Gate3DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["continue"]
    exclusions: list[Gate3ExclusionRequest] = []


class Gate4DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    snapshot_hash: str
    snapshot_revision: StrictInt
    reason: str | None = None


class AdvisorAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=100)
    answer_type: Literal["manual", "file", "public_research", "skip"]
    value: str | None = Field(default=None, max_length=2000)
    document_id: str | None = Field(default=None, min_length=1, max_length=100)
    consent_public_research: bool = False

    @model_validator(mode="after")
    def validate_answer_shape(self) -> "AdvisorAnswerRequest":
        if self.answer_type == "manual":
            if self.value is None or not self.value.strip() or self.document_id is not None:
                raise ValueError("invalid manual advisor answer")
        elif self.value is not None:
            raise ValueError("advisor answer value is only valid for manual mode")
        if self.answer_type == "file":
            if self.document_id is None:
                raise ValueError("file advisor answer requires document_id")
        elif self.document_id is not None:
            raise ValueError("document_id is only valid for file mode")
        return self


class AdvisorImprovementDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected"]


@router.post("/cases", response_model=StartupCaseResponse, status_code=201)
def create_case(
    request: StartupCreateRequest,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupCaseResponse:
    return coordinator.create_case(request.model_dump())


@router.get("/cases/{case_id}", response_model=StartupStatusResponse)
def get_case(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupStatusResponse:
    return coordinator.get_status(case_id)


@router.post("/cases/{case_id}/documents", response_model=StartupUploadResponse)
async def upload_documents(
    case_id: str,
    files: list[UploadFile] = File(default_factory=list),
    auto_start: bool = Form(...),
    company_name: str | None = Form(default=None),
    website: str | None = Form(default=None),
    as_of: str | None = Form(default=None),
    document_class_hint: str | None = Form(default=None),
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupUploadResponse:
    safe_files = [
        {
            "content": await file.read(),
            "content_type": file.content_type,
            "filename": file.filename,
        }
        for file in files
    ]
    return coordinator.upload_documents(
        case_id,
        files=safe_files,
        auto_start=auto_start,
        metadata={
            "company_name": company_name,
            "website": website,
            "as_of": as_of,
            "document_class_hint": document_class_hint,
        },
    )


@router.get("/cases/{case_id}/analysis", response_model=StartupStatusResponse)
def get_analysis(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupStatusResponse:
    return coordinator.get_analysis(case_id)


@router.get("/cases/{case_id}/profile", response_model=StartupProfileResponse)
def get_profile(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupProfileResponse:
    return coordinator.get_profile(case_id)


@router.get("/cases/{case_id}/gtm", response_model=StartupGtmResponse)
def get_gtm(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupGtmResponse:
    return coordinator.get_gtm(case_id)


@router.get("/cases/{case_id}/gate2/preview", response_model=StartupGate2PreviewResponse)
def get_gate2_preview(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupGate2PreviewResponse:
    return coordinator.get_gate2_preview(case_id)


@router.post("/cases/{case_id}/gate2/decision", response_model=StartupDecisionResponse)
def decide_gate2(
    case_id: str,
    request: Gate2DecisionRequest,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupDecisionResponse:
    return coordinator.decide_gate2(case_id, request.model_dump())


@router.post("/cases/{case_id}/gate3/decision", response_model=StartupDecisionResponse)
def decide_gate3(
    case_id: str,
    request: Gate3DecisionRequest,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupDecisionResponse:
    return coordinator.decide_gate3(case_id, request.model_dump())


@router.post("/cases/{case_id}/gate4/decision", response_model=StartupDecisionResponse)
def decide_gate4(
    case_id: str,
    request: Gate4DecisionRequest,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupDecisionResponse:
    return coordinator.decide_gate4(case_id, request.model_dump())


@router.get("/cases/{case_id}/report", response_model=StartupReportResponse)
def get_report(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> StartupReportResponse:
    return coordinator.get_report(case_id)


@router.get("/cases/{case_id}/report/json", response_class=Response)
def get_report_json(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> Response:
    return Response(coordinator.get_report_json(case_id), media_type="application/json")


@router.get("/cases/{case_id}/report/html", response_class=HTMLResponse)
def get_report_html(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> HTMLResponse:
    return HTMLResponse(coordinator.get_report_html(case_id))


@router.get("/cases/{case_id}/report/pdf", response_class=Response)
def get_report_pdf(
    case_id: str,
    coordinator: StartupCaseCoordinator = Depends(get_startup_case_coordinator),
) -> Response:
    return Response(coordinator.get_report_pdf(case_id), media_type="application/pdf")


@router.get(
    "/cases/{case_id}/advisor/next-question",
    response_model=AdvisorNextQuestionResponse,
)
def get_advisor_next_question(
    case_id: str,
    service: StartupAdvisorApiService = Depends(get_startup_advisor_api_service),
) -> AdvisorNextQuestionResponse:
    return service.get_next_question(case_id)


@router.post(
    "/cases/{case_id}/advisor/answers",
    response_model=AdvisorAnswerResponse,
)
def submit_advisor_answer(
    case_id: str,
    request: AdvisorAnswerRequest,
    service: StartupAdvisorApiService = Depends(get_startup_advisor_api_service),
) -> AdvisorAnswerResponse:
    return service.submit_answer(case_id, **request.model_dump())


@router.get(
    "/cases/{case_id}/advisor/improvements",
    response_model=StartupImprovementsResponse,
)
def get_advisor_improvements(
    case_id: str,
    service: StartupAdvisorApiService = Depends(get_startup_advisor_api_service),
) -> StartupImprovementsResponse:
    return service.list_improvements(case_id)


@router.post(
    "/cases/{case_id}/advisor/improvements/{proposal_id}/decision",
    response_model=StartupImprovementDecisionResponse,
)
def decide_advisor_improvement(
    case_id: str,
    proposal_id: UUID,
    request: AdvisorImprovementDecisionRequest,
    service: StartupAdvisorApiService = Depends(get_startup_advisor_api_service),
) -> StartupImprovementDecisionResponse:
    return service.decide_improvement(
        case_id,
        proposal_id=proposal_id,
        decision=request.decision,
    )


async def startup_error_response(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StartupError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.code},
    )


async def request_validation_error_response(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return JSONResponse(
        status_code=422,
        content={
            "code": "request_validation_error",
            "message": "request_validation_error",
        },
    )
