from decimal import Decimal
from time import perf_counter
from typing import Any

import litellm

from editorial_os_api.model_gateway.contracts import (
    ModelRequest,
    ModelRoute,
    RawModelResponse,
)


class LiteLLMClient:
    """LiteLLM-backed adapter behind the provider-agnostic ModelClient protocol."""

    def complete(
        self,
        request: ModelRequest,
        route: ModelRoute,
        *,
        json_schema: dict[str, object] | None = None,
    ) -> RawModelResponse:
        messages = [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in request.messages
        ]
        kwargs: dict[str, Any] = {
            "model": route.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "timeout": route.timeout_seconds,
            "max_retries": route.max_retries,
            "stream": False,
        }
        if json_schema is not None and route.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        started = perf_counter()
        response = litellm.completion(**kwargs)
        latency_ms = max(0, round((perf_counter() - started) * 1000))

        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("LiteLLM response contained no choices.")

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            raise RuntimeError("LiteLLM response contained no text content.")

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        hidden = getattr(response, "_hidden_params", {})
        raw_cost = hidden.get("response_cost") if isinstance(hidden, dict) else None
        cost = Decimal(str(raw_cost)) if raw_cost is not None else None

        model = getattr(response, "model", route.model)
        if not isinstance(model, str):
            model = route.model

        return RawModelResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
