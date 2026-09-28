import logging

from editorial_os_api.config import Settings
from editorial_os_api.observability.adapters import (
    LangfuseTelemetrySink,
    PostHogTelemetrySink,
)
from editorial_os_api.observability.contracts import TelemetrySink
from editorial_os_api.observability.hub import ObservabilityHub
from editorial_os_api.observability.logging import log_event


def build_observability(settings: Settings) -> ObservabilityHub:
    logger = logging.getLogger("editorial_os.observability.factory")
    sinks: list[TelemetrySink] = []

    if settings.langfuse_enabled:
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            sinks.append(
                LangfuseTelemetrySink(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    base_url=settings.langfuse_base_url,
                    environment=settings.environment,
                    capture_model_io=settings.langfuse_capture_model_io,
                )
            )
        else:
            log_event(
                logger,
                "telemetry.langfuse_disabled_invalid_config",
                level=logging.WARNING,
                properties={"reason": "missing credentials"},
            )

    if settings.posthog_enabled:
        if settings.posthog_project_token:
            sinks.append(
                PostHogTelemetrySink(
                    project_token=settings.posthog_project_token,
                    host=settings.posthog_host,
                )
            )
        else:
            log_event(
                logger,
                "telemetry.posthog_disabled_invalid_config",
                level=logging.WARNING,
                properties={"reason": "missing project token"},
            )

    return ObservabilityHub(tuple(sinks))
