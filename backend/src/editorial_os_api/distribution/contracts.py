from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ChannelVariant:
    channel: str
    integration_id: str
    content: str
    settings: dict[str, object] = field(default_factory=dict)
    media: tuple[str, ...] = ()
    scheduled_at: datetime | None = None


@dataclass(frozen=True)
class DistributionReceipt:
    external_id: str
    status: str
    external_url: str | None = None
    scheduled_at: datetime | None = None
    raw: dict[str, object] = field(default_factory=dict)


class DistributionRetryableError(RuntimeError):
    pass


class DistributionTerminalError(RuntimeError):
    pass


class DistributionReconciliationRequired(RuntimeError):
    pass


class DistributionAdapter(Protocol):
    name: str

    def deliver(
        self,
        variant: ChannelVariant,
        *,
        owner_key: str,
        idempotency_key: str,
    ) -> DistributionReceipt: ...


class PeripheralWorkflowAdapter(Protocol):
    name: str

    def trigger(
        self,
        event_name: str,
        payload: dict[str, object],
        *,
        idempotency_key: str,
    ) -> dict[str, object]: ...
