from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from editorial_os_api.config import Settings, get_settings
from editorial_os_api.db import check_database
from editorial_os_api.observability.factory import build_observability
from editorial_os_api.observability.http import CorrelationMiddleware
from editorial_os_api.observability.logging import configure_structured_logging
from editorial_os_api.operator_console import router as operator_router
from editorial_os_api.pilot.router import router as pilot_router


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str
    deployment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_structured_logging()
    observability = build_observability(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            observability.shutdown()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.observability = observability
    application.state.settings = settings
    application.add_middleware(CorrelationMiddleware)
    application.include_router(operator_router)
    application.include_router(pilot_router)

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            environment=settings.environment,
            deployment=settings.deployment_label,
        )

    @application.get("/health/ready", response_model=ReadinessResponse, tags=["system"])
    def readiness() -> ReadinessResponse:
        try:
            check_database(settings)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not ready.",
            ) from exc
        return ReadinessResponse(status="ready")

    return application


app = create_app()
