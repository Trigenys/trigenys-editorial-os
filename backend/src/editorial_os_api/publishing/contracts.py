from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class CMSAsset:
    slot: str
    kind: str
    uri: str | None
    alt_text: str | None
    caption: str | None
    filename: str | None
    rights_status: str


@dataclass(frozen=True)
class CMSDocument:
    title: str
    deck: str | None
    body: str
    locale: str
    metadata: dict[str, Any] = field(default_factory=dict)
    assets: tuple[CMSAsset, ...] = ()


@dataclass(frozen=True)
class CMSDraftReceipt:
    external_id: str
    external_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CMSPublishReceipt:
    external_id: str
    external_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class CMSRetryableError(RuntimeError):
    pass


class CMSTerminalError(RuntimeError):
    pass


class CMSAdapter(Protocol):
    name: str

    def upsert_draft(
        self,
        document: CMSDocument,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
        existing_external_id: str | None,
    ) -> CMSDraftReceipt: ...

    def publish(
        self,
        external_id: str,
        *,
        target: str,
        owner_key: str,
        idempotency_key: str,
    ) -> CMSPublishReceipt: ...
