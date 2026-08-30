from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from due_diligence_agent.presentation.api.middleware import (
    RequestContextMiddleware,
    unhandled_exception_response,
)
from due_diligence_agent.application.startup_cases import StartupError
from due_diligence_agent.presentation.api.routers.startup import (
    request_validation_error_response,
    router as startup_router,
    startup_error_response,
)
from due_diligence_agent.presentation.api.routers.startup_copilot import (
    router as startup_copilot_router,
)
from due_diligence_agent.presentation.api.routers.system import router as system_router


def create_app() -> FastAPI:
    """Create the API app without booting storage, embeddings, or workflows."""

    app = FastAPI(
        title="Founder Launch Intelligence API",
        version="1.0.0",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_response)
    app.add_exception_handler(StartupError, startup_error_response)
    app.add_exception_handler(RequestValidationError, request_validation_error_response)
    app.include_router(system_router)
    app.include_router(startup_router)
    app.include_router(startup_copilot_router)
    return app
