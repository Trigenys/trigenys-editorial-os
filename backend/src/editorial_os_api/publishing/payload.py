from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx

from editorial_os_api.publishing.contracts import (
    CMSDocument,
    CMSDraftReceipt,
    CMSPublishReceipt,
    CMSRetryableError,
    CMSTerminalError,
)


class PayloadDocumentMapper(Protocol):
    def map_document(self, document: CMSDocument) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PayloadPostMapper:
    """Map the provider-neutral document to a conventional Payload post."""

    static_fields: Mapping[str, Any] = field(default_factory=dict)
    title_field: str = "title"
    excerpt_field: str = "excerpt"
    content_field: str = "content"
    seo_field: str | None = "meta"
    assets_field: str | None = "editorialAssets"

    def map_document(self, document: CMSDocument) -> dict[str, Any]:
        mapped: dict[str, Any] = dict(self.static_fields)
        mapped[self.title_field] = document.title
        mapped[self.excerpt_field] = self._excerpt(document)
        mapped[self.content_field] = _lexical_document(document.body)

        if self.seo_field:
            seo = document.metadata.get("seo")
            if isinstance(seo, dict):
                meta: dict[str, Any] = {}
                title = seo.get("title") or seo.get("metaTitle")
                description = seo.get("description") or seo.get("metaDescription")
                if title:
                    meta["title"] = title
                if description:
                    meta["description"] = description
                if meta:
                    mapped[self.seo_field] = meta

        if self.assets_field:
            mapped[self.assets_field] = [
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
            ]
        return mapped

    @staticmethod
    def _excerpt(document: CMSDocument) -> str:
        if document.deck and document.deck.strip():
            return document.deck.strip()[:320]
        compact = " ".join(document.body.split())
        return compact[:320]


class PayloadCMSAdapter:
    """Payload REST adapter with explicit auth, locale and ownership semantics."""

    name = "payload"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        auth_collection: str = "users",
        bearer_token: str | None = None,
        collection: str = "posts",
        mapper: PayloadDocumentMapper | None = None,
        owner_field: str = "editorialOwnerKey",
        publication_key_field: str = "editorialPublicationKey",
        target_field: str = "editorialTarget",
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if bool(api_key) == bool(bearer_token):
            raise ValueError(
                "Configure exactly one Payload credential: api_key or bearer_token."
            )
        self.base_url = base_url.rstrip("/")
        self.collection = collection.strip("/")
        self.owner_field = owner_field
        self.publication_key_field = publication_key_field
        self.target_field = target_field
        self.mapper = mapper or PayloadPostMapper()
        self._authorization = (
            f"{auth_collection.strip('/')} API-Key {api_key}"
            if api_key
            else f"Bearer {bearer_token}"
        )
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
        payload = self.mapper.map_document(document)
        payload.update(
            {
                "_status": "draft",
                self.owner_field: owner_key,
                self.publication_key_field: idempotency_key,
                self.target_field: target,
            }
        )
        params = self._draft_params(document.locale)

        external_id = existing_external_id or self._find_owned_draft(
            owner_key,
            locale=document.locale,
        )
        if external_id:
            response = self._request(
                "PATCH",
                f"/api/{self.collection}/{external_id}",
                params=params,
                json=payload,
            )
        else:
            response = self._request(
                "POST",
                f"/api/{self.collection}",
                params=params,
                json=payload,
            )

        data = self._extract_doc(response)
        resolved_id = str(data.get("id") or external_id or "")
        if not resolved_id:
            raise CMSTerminalError(
                "Payload draft response did not include a document id."
            )

        return CMSDraftReceipt(
            external_id=resolved_id,
            external_url=self._preview_url(data),
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
                "Scheduled publish needs a target-specific Payload jobs endpoint; "
                "the generic REST adapter will not invent scheduling semantics."
            )

        response = self._request(
            "PATCH",
            f"/api/{self.collection}/{external_id}",
            params={
                "locale": document.locale,
                "draft": "false",
                "depth": "0",
            },
            json={
                "_status": "published",
                self.owner_field: owner_key,
                self.publication_key_field: idempotency_key,
                self.target_field: target,
            },
        )
        data = self._extract_doc(response)
        return CMSPublishReceipt(
            external_id=str(data.get("id") or external_id),
            status="PUBLISHED",
            external_url=self._published_url(data),
            raw=data,
        )

    def _find_owned_draft(
        self,
        owner_key: str,
        *,
        locale: str,
    ) -> str | None:
        response = self._request(
            "GET",
            f"/api/{self.collection}",
            params={
                f"where[{self.owner_field}][equals]": owner_key,
                "draft": "true",
                "locale": locale,
                "depth": "0",
                "limit": "1",
            },
        )
        data = response.json()
        docs = data.get("docs", []) if isinstance(data, dict) else []
        if not isinstance(docs, list) or not docs:
            return None
        first = docs[0]
        if not isinstance(first, dict):
            return None
        value = first.get("id")
        return str(value) if value is not None else None

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": self._authorization,
                    "Content-Type": "application/json",
                },
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise CMSRetryableError(f"Payload request failed: {exc}") from exc

        if response.status_code >= 500 or response.status_code in {
            408,
            409,
            425,
            429,
        }:
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
    def _draft_params(locale: str) -> dict[str, str]:
        return {
            "draft": "true",
            "locale": locale,
            "depth": "0",
        }

    @staticmethod
    def _extract_doc(response: httpx.Response) -> dict[str, Any]:
        data = response.json()
        if not isinstance(data, dict):
            raise CMSTerminalError("Payload response was not an object.")
        doc = data.get("doc", data)
        if not isinstance(doc, dict):
            raise CMSTerminalError(
                "Payload response did not contain a document."
            )
        return doc

    @staticmethod
    def _preview_url(data: dict[str, Any]) -> str | None:
        value = data.get("previewURL") or data.get("previewUrl")
        return str(value) if value else None

    @staticmethod
    def _published_url(data: dict[str, Any]) -> str | None:
        value = (
            data.get("url")
            or data.get("canonicalURL")
            or data.get("canonicalUrl")
        )
        return str(value) if value else PayloadCMSAdapter._preview_url(data)


def _lexical_document(source: str) -> dict[str, Any]:
    blocks = [
        " ".join(block.split())
        for block in source.strip().split("\n\n")
        if block.strip()
    ]
    children: list[dict[str, Any]] = []
    for block in blocks:
        if block.startswith(("## ", "### ", "#### ")):
            level = len(block) - len(block.lstrip("#"))
            text = block[level:].strip()
            children.append(
                {
                    "children": [_text_node(text)],
                    "direction": "ltr",
                    "format": "",
                    "indent": 0,
                    "tag": f"h{level}",
                    "type": "heading",
                    "version": 1,
                }
            )
            continue
        children.append(
            {
                "children": [_text_node(block)],
                "direction": "ltr",
                "format": "",
                "indent": 0,
                "textFormat": 0,
                "type": "paragraph",
                "version": 1,
            }
        )
    return {
        "root": {
            "children": children,
            "direction": "ltr",
            "format": "",
            "indent": 0,
            "type": "root",
            "version": 1,
        }
    }


def _text_node(text: str) -> dict[str, Any]:
    return {
        "detail": 0,
        "format": 0,
        "mode": "normal",
        "style": "",
        "text": text,
        "type": "text",
        "version": 1,
    }
