from __future__ import annotations

from typing import Any

import httpx

from editorial_os_api.publishing.contracts import (
    CMSDocument,
    CMSDraftReceipt,
    CMSPublishReceipt,
    CMSRetryableError,
    CMSTerminalError,
)


class PayloadCMSAdapter:
    """Payload adapter that owns only transport/provider semantics."""

    name = "payload"

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        collection: str = "posts",
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.collection = collection.strip("/")
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
        payload = self._document_payload(
            document,
            owner_key=owner_key,
            idempotency_key=idempotency_key,
            target=target,
        )

        external_id = existing_external_id or self._find_owned_draft(owner_key)
        if external_id:
            response = self._request(
                "PATCH",
                f"/api/{self.collection}/{external_id}",
                json=payload,
            )
        else:
            response = self._request(
                "POST",
                f"/api/{self.collection}",
                json=payload,
            )

        data = self._extract_doc(response)
        resolved_id = str(data.get("id") or external_id or "")
        if not resolved_id:
            raise CMSTerminalError("Payload draft response did not include a document id.")

        return CMSDraftReceipt(
            external_id=resolved_id,
            external_url=self._preview_url(data),
            raw=data,
        )

    def publish(
        self,
        external_id: str,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
    ) -> CMSPublishReceipt:
        response = self._request(
            "PATCH",
            f"/api/{self.collection}/{external_id}",
            json={
                "_status": "published",
                "ownerKey": owner_key,
                "publicationKey": idempotency_key,
                "editorialTarget": target,
            },
        )
        data = self._extract_doc(response)
        return CMSPublishReceipt(
            external_id=str(data.get("id") or external_id),
            external_url=self._published_url(data),
            raw=data,
        )

    def _find_owned_draft(self, owner_key: str) -> str | None:
        response = self._request(
            "GET",
            f"/api/{self.collection}",
            params={
                "where[ownerKey][equals]": owner_key,
                "limit": "1",
                "depth": "0",
            },
        )
        data = response.json()
        docs = data.get("docs", []) if isinstance(data, dict) else []
        if not docs:
            return None
        first = docs[0]
        return str(first["id"]) if isinstance(first, dict) and first.get("id") else None

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                },
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise CMSRetryableError(f"Payload request failed: {exc}") from exc

        if response.status_code >= 500 or response.status_code in {408, 409, 425, 429}:
            raise CMSRetryableError(
                f"Payload returned retryable HTTP {response.status_code}."
            )
        if response.status_code >= 400:
            raise CMSTerminalError(
                f"Payload returned terminal HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        return response

    @staticmethod
    def _document_payload(
        document: CMSDocument,
        *,
        owner_key: str,
        idempotency_key: str,
        target: str,
    ) -> dict[str, Any]:
        return {
            "title": document.title,
            "deck": document.deck,
            "body": document.body,
            "locale": document.locale,
            "_status": "draft",
            "ownerKey": owner_key,
            "publicationKey": idempotency_key,
            "editorialTarget": target,
            "metadata": document.metadata,
            "assets": [
                {
                    "slot": asset.slot,
                    "kind": asset.kind,
                    "uri": asset.uri,
                    "altText": asset.alt_text,
                    "caption": asset.caption,
                    "filename": asset.filename,
                    "rightsStatus": asset.rights_status,
                }
                for asset in document.assets
            ],
        }

    @staticmethod
    def _extract_doc(response: httpx.Response) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            raise CMSTerminalError("Payload response was not an object.")
        doc = data.get("doc", data)
        if not isinstance(doc, dict):
            raise CMSTerminalError("Payload response did not contain a document.")
        return doc

    @staticmethod
    def _preview_url(data: dict[str, Any]) -> str | None:
        value = data.get("previewURL") or data.get("previewUrl")
        return str(value) if value else None

    @staticmethod
    def _published_url(data: dict[str, Any]) -> str | None:
        value = data.get("url") or data.get("canonicalURL") or data.get("canonicalUrl")
        return str(value) if value else PayloadCMSAdapter._preview_url(data)
