from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import httpx

from editorial_os_api.distribution.contracts import (
    ChannelVariant,
    DistributionReceipt,
    DistributionReconciliationRequired,
    DistributionRetryableError,
    DistributionTerminalError,
)


class PostizAdapter:
    """Thin adapter around the Postiz public REST API."""

    name = "postiz"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.postiz.com/public/v1",
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Postiz api_key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def deliver(
        self,
        variant: ChannelVariant,
        *,
        owner_key: str,
        idempotency_key: str,
    ) -> DistributionReceipt:
        scheduled_at = variant.scheduled_at or datetime.now(UTC)
        payload: dict[str, object] = {
            "type": "schedule",
            "date": scheduled_at.isoformat().replace("+00:00", "Z"),
            "shortLink": False,
            "tags": [],
            "posts": [
                {
                    "integration": {"id": variant.integration_id},
                    "value": [
                        {
                            "content": variant.content,
                            "image": [
                                {"path": media_url}
                                for media_url in variant.media
                            ],
                        }
                    ],
                    "settings": {
                        "__type": variant.channel,
                        **variant.settings,
                    },
                }
            ],
        }

        try:
            response = self._client.post(
                f"{self.base_url}/posts",
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                    "X-Editorial-Owner": owner_key,
                },
                json=payload,
            )
        except httpx.ConnectError as exc:
            raise DistributionRetryableError(
                f"Postiz connection failed before delivery: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DistributionReconciliationRequired(
                "Postiz delivery outcome is ambiguous after a transport error."
            ) from exc

        if response.status_code in {425, 429}:
            raise DistributionRetryableError(
                f"Postiz rejected the request with retryable HTTP {response.status_code}."
            )
        if response.status_code >= 500 or response.status_code == 408:
            raise DistributionReconciliationRequired(
                f"Postiz returned ambiguous HTTP {response.status_code}; "
                "reconcile before retrying."
            )
        if response.status_code >= 400:
            raise DistributionTerminalError(
                f"Postiz returned terminal HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        data = cast(object, response.json())
        normalized = _normalize_response(data)
        external_id = _first_string(
            normalized,
            "id",
            "postId",
            "post_id",
        )
        if external_id is None:
            external_id = idempotency_key

        external_url = _first_string(normalized, "url", "postUrl", "post_url")
        return DistributionReceipt(
            external_id=external_id,
            status="SCHEDULED",
            external_url=external_url,
            scheduled_at=scheduled_at,
            raw=normalized,
        )


def _normalize_response(data: object) -> dict[str, object]:
    if isinstance(data, dict):
        return {str(key): cast(object, value) for key, value in data.items()}
    if isinstance(data, list):
        return {"items": cast(object, data)}
    return {"value": str(data)}


def _first_string(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (str, int)):
            return str(value)

    items = payload.get("items")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            for key in keys:
                value = first.get(key)
                if isinstance(value, (str, int)):
                    return str(value)
    return None
