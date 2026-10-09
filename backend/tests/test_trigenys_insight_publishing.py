from __future__ import annotations

import json

import httpx
import pytest

from editorial_os_api.publishing import (
    CMSDocument,
    CMSTerminalError,
    TrigenysInsightCMSAdapter,
)


def _document() -> CMSDocument:
    return CMSDocument(
        title="Pilot article",
        deck="A staging excerpt",
        body="First paragraph.\n\nSecond paragraph.",
        locale="fr",
        metadata={"seo": {"title": "Pilot SEO", "description": "Pilot description"}},
    )


def test_staging_adapter_upserts_draft_with_stable_idempotency_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "id": 42,
                "status": "DRAFT",
                "previewURL": "/fr/posts/editorial-os-test",
            },
        )

    adapter = TrigenysInsightCMSAdapter(
        base_url="https://insight.example.test",
        bearer_token="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    receipt = adapter.upsert_draft(
        _document(),
        target="trigenys-insight-staging",
        owner_key="editorial-os:test",
        idempotency_key="publication:test",
        existing_external_id=None,
    )

    assert receipt.external_id == "42"
    assert receipt.external_url == "https://insight.example.test/fr/posts/editorial-os-test"
    assert len(requests) == 1
    assert requests[0].url.path == "/api/editorial-os"
    assert requests[0].headers["authorization"] == "Bearer secret"

    payload = json.loads(requests[0].content)
    assert payload["operation"] == "draft"
    assert payload["idempotencyKey"] == "publication:test"
    assert payload["ownerKey"] == "editorial-os:test"


def test_staging_adapter_publish_uses_same_idempotency_key() -> None:
    operations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        operations.append(payload["operation"])
        return httpx.Response(
            200,
            json={
                "ok": True,
                "id": 42,
                "status": "PUBLISHED",
                "url": "/fr/posts/editorial-os-test",
            },
        )

    adapter = TrigenysInsightCMSAdapter(
        base_url="https://insight.example.test/",
        bearer_token="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    receipt = adapter.publish(
        _document(),
        "42",
        target="trigenys-insight-staging",
        owner_key="editorial-os:test",
        idempotency_key="publication:test",
    )

    assert operations == ["publish"]
    assert receipt.external_id == "42"
    assert receipt.status == "PUBLISHED"
    assert receipt.external_url == "https://insight.example.test/fr/posts/editorial-os-test"


def test_staging_adapter_rejects_scheduled_publish() -> None:
    adapter = TrigenysInsightCMSAdapter(
        base_url="https://insight.example.test",
        bearer_token="secret",
    )

    with pytest.raises(CMSTerminalError, match="does not schedule"):
        adapter.publish(
            _document(),
            "42",
            target="trigenys-insight-staging",
            owner_key="editorial-os:test",
            idempotency_key="publication:test",
            scheduled_at=__import__("datetime").datetime.now(
                __import__("datetime").UTC
            ),
        )
