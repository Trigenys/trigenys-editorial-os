from __future__ import annotations

from typing import cast

import httpx

from editorial_os_api.distribution.contracts import (
    DistributionRetryableError,
    DistributionTerminalError,
)


class N8nWebhookAdapter:
    """Optional boundary for peripheral workflows; never owns core workflow state."""

    name = "n8n"

    def __init__(
        self,
        *,
        webhook_url: str,
        bearer_token: str | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.webhook_url = webhook_url
        self.bearer_token = bearer_token
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def trigger(
        self,
        event_name: str,
        payload: dict[str, object],
        *,
        idempotency_key: str,
    ) -> dict[str, object]:
        headers = {
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key,
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        try:
            response = self._client.post(
                self.webhook_url,
                headers=headers,
                json={
                    "event": event_name,
                    "idempotency_key": idempotency_key,
                    "payload": payload,
                },
            )
        except httpx.HTTPError as exc:
            raise DistributionRetryableError(f"n8n webhook failed: {exc}") from exc

        if response.status_code >= 500 or response.status_code in {408, 425, 429}:
            raise DistributionRetryableError(
                f"n8n returned retryable HTTP {response.status_code}."
            )
        if response.status_code >= 400:
            raise DistributionTerminalError(
                f"n8n returned terminal HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        if not response.content:
            return {"status_code": response.status_code}
        data = cast(object, response.json())
        if isinstance(data, dict):
            return {str(key): cast(object, value) for key, value in data.items()}
        return {"value": cast(object, data)}
