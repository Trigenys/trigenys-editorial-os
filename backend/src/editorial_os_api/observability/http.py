import logging
from uuid import UUID, uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from editorial_os_api.observability.context import bind_correlation
from editorial_os_api.observability.logging import log_event


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        workflow_run_id = self._workflow_run_id(request)

        with bind_correlation(
            request_id=request_id,
            workflow_run_id=workflow_run_id,
        ) as context:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            if context.correlation_id is not None:
                response.headers["X-Correlation-ID"] = context.correlation_id
            return response

    @staticmethod
    def _workflow_run_id(request: Request) -> UUID | None:
        raw = request.headers.get("x-workflow-run-id")
        if raw is None:
            return None
        try:
            return UUID(raw)
        except ValueError:
            log_event(
                logging.getLogger("editorial_os.http"),
                "http.invalid_workflow_run_id",
                level=logging.WARNING,
                properties={"header_present": True},
            )
            return None
