from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from due_diligence_agent.application.product.capabilities import (
    ProductCapabilities,
    ProductCapabilitiesService,
)
from due_diligence_agent.presentation.api.context import RequestContext
from due_diligence_agent.presentation.api.dependencies import (
    get_product_capabilities_service,
    get_request_context,
)

router = APIRouter()


class HealthLiveResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]


@router.get("/health/live", response_model=HealthLiveResponse)
def health_live() -> HealthLiveResponse:
    return HealthLiveResponse(status="ok")


@router.get("/api/v1/product/capabilities", response_model=ProductCapabilities)
def product_capabilities(
    _context: RequestContext = Depends(get_request_context),
    service: ProductCapabilitiesService = Depends(get_product_capabilities_service),
) -> ProductCapabilities:
    return service.get_capabilities()
