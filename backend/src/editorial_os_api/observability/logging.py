import json
import logging
from datetime import UTC, datetime
from typing import Any

from editorial_os_api.observability.context import current_correlation
from editorial_os_api.observability.redaction import redact, redact_text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = current_correlation()
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        if context.correlation_id is not None:
            payload["correlation_id"] = context.correlation_id
        if context.request_id is not None:
            payload["request_id"] = context.request_id
        if context.workflow_run_id is not None:
            payload["workflow_run_id"] = str(context.workflow_run_id)
        if context.agent_id is not None:
            payload["agent_id"] = context.agent_id
        if context.call_key is not None:
            payload["call_key"] = context.call_key

        event_name = getattr(record, "event_name", None)
        if isinstance(event_name, str):
            payload["event"] = event_name

        event_data = getattr(record, "event_data", None)
        if event_data is not None:
            payload["data"] = redact(event_data)

        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__

        return json.dumps(payload, default=str, sort_keys=True)


def configure_structured_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    if any(getattr(handler, "_editorial_os_json", False) for handler in root.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._editorial_os_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)


def log_event(
    logger: logging.Logger,
    event_name: str,
    *,
    level: int = logging.INFO,
    properties: dict[str, object] | None = None,
    exc_info: Any = None,
) -> None:
    logger.log(
        level,
        event_name,
        extra={
            "event_name": event_name,
            "event_data": redact(properties or {}),
        },
        exc_info=exc_info,
    )
