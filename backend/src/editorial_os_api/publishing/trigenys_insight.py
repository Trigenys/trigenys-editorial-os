from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from editorial_os_api.publishing.contracts import (
    CMSDocument,
    CMSDraftReceipt,
    CMSPublishReceipt,
    CMSRetryableError,
    CMSTerminalError,
)


class TrigenysInsightCMSAdapter:
    """Staging-only adapter for the hardened Trigenys Insight ingestion endpoint."""

    name = "trigenys-insight"

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not bearer_token.strip():
            raise ValueError("A bearer token is required.")
        self.base_url = base_url.rstrip("/")
        self._authorization = f"Bearer {bearer_token}"
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def upsert_draft(
        self,
        document: CMSDocument,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
        existing_external_id: str | None,
    ) -> CMSDraftReceipt:
        data = self._request(
            document,
            operation="draft",
            target=target,
            owner_key=owner_key,
            idempotency_key=idempotency_key,
        )
        external_id = str(data.get("id") or existing_external_id or "")
        if not external_id:
            raise CMSTerminalError(
                "Trigenys Insight staging response did not include a document id."
            )
        return CMSDraftReceipt(
            external_id=external_id,
            external_url=self._absolute_url(data.get("previewURL")),
            raw=data,
        )

    def publish(
        self,
        document: CMSDocument,
        external_id: str,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
        scheduled_at: datetime | None = None,
    ) -> CMSPublishReceipt:
        if scheduled_at is not None:
            raise CMSTerminalError(
                "The Trigenys Insight staging adapter does not schedule publication."
            )
        data = self._request(
            document,
            operation="publish",
            target=target,
            owner_key=owner_key,
            idempotency_key=idempotency_key,
        )
        resolved_id = str(data.get("id") or external_id)
        return CMSPublishReceipt(
            external_id=resolved_id,
            status=str(data.get("status") or "PUBLISHED"),
            external_url=self._absolute_url(data.get("url")),
            raw=data,
        )

    def _request(
        self,
        document: CMSDocument,
        *,
        operation: str,
        target: str,
        owner_key: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {
            "operation": operation,
            "idempotencyKey": idempotency_key,
            "ownerKey": owner_key,
            "target": target,
            "locale": document.locale,
            "title": document.title,
            "excerpt": document.deck,
            "body": document.body,
            "metadata": document.metadata,
        }
        try:
            response = self._client.post(
                f"{self.base_url}/api/editorial-os",
                headers={
                    "Authorization": self._authorization,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise CMSRetryableError(
                f"Trigenys Insight staging request failed: {exc}"
            ) from exc

        if response.status_code >= 500 or response.status_code in {
            408,
            409,
            425,
            429,
        }:
            raise CMSRetryableError(
                "Trigenys Insight staging returned retryable HTTP "
                f"{response.status_code}."
            )
        if response.status_code >= 400:
            raise CMSTerminalError(
                "Trigenys Insight staging returned terminal HTTP "
                f"{response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        if not isinstance(data, dict):
            raise CMSTerminalError(
                "Trigenys Insight staging response was not an object."
            )
        return data

    def _absolute_url(self, value: object | None) -> str | None:
        if not value:
            return None
        raw = str(value)
        if raw.startswith(("http://", "https://")):
            return raw
        return f"{self.base_url}/{raw.lstrip('/')}"
