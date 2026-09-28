from collections import deque
from decimal import Decimal

from editorial_os_api.model_gateway.contracts import (
    ModelRequest,
    ModelRoute,
    RawModelResponse,
)


class DeterministicFakeModel:
    """Scripted model double for CI and local deterministic tests."""

    def __init__(
        self,
        responses: list[str],
        *,
        input_tokens: int = 11,
        output_tokens: int = 7,
        cost_usd: Decimal = Decimal("0.001"),
        latency_ms: int = 5,
    ) -> None:
        self._responses = deque(responses)
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._cost_usd = cost_usd
        self._latency_ms = latency_ms
        self.calls: list[tuple[ModelRequest, ModelRoute, dict[str, object] | None]] = []

    def complete(
        self,
        request: ModelRequest,
        route: ModelRoute,
        *,
        json_schema: dict[str, object] | None = None,
    ) -> RawModelResponse:
        if not self._responses:
            raise RuntimeError("DeterministicFakeModel has no scripted response left.")

        self.calls.append((request, route, json_schema))
        return RawModelResponse(
            content=self._responses.popleft(),
            model=route.model,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cost_usd=self._cost_usd,
            latency_ms=self._latency_ms,
        )
