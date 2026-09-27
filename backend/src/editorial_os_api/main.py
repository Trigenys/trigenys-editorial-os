from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from editorial_os_api.config import get_settings
from editorial_os_api.db import check_database


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"]


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
    )

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            environment=settings.environment,
        )

    @application.get("/health/ready", response_model=ReadinessResponse, tags=["system"])
    def readiness() -> ReadinessResponse:
        try:
            check_database()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not ready.",
            ) from exc
        return ReadinessResponse(status="ready")

    return application


app = create_app()
