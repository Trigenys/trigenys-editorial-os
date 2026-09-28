from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import EvidenceTier, SourceHealthStatus, SourceKind
from editorial_os_api.persistence.models import Source
from editorial_os_api.scout.contracts import (
    FetchPolicy,
    SourceRegistration,
    SourceSnapshot,
)


def apply_source_success(
    source: Source,
    *,
    policy: FetchPolicy,
    now: datetime,
    cursor: str | None,
) -> None:
    source.health_status = SourceHealthStatus.HEALTHY.value
    source.consecutive_failures = 0
    source.last_success_at = now
    source.last_error_kind = None
    source.next_fetch_at = now + timedelta(seconds=policy.interval_seconds)
    if cursor is not None:
        source.cursor = cursor


def apply_source_failure(
    source: Source,
    *,
    policy: FetchPolicy,
    now: datetime,
    error_kind: str,
    retryable: bool,
) -> None:
    source.consecutive_failures += 1
    source.last_failure_at = now
    source.last_error_kind = error_kind

    should_pause = (
        not retryable
        or source.consecutive_failures >= policy.max_failures_before_pause
    )
    if should_pause:
        source.health_status = SourceHealthStatus.PAUSED.value
        source.next_fetch_at = None
        return

    source.health_status = SourceHealthStatus.DEGRADED.value
    backoff = min(
        policy.max_backoff_seconds,
        policy.interval_seconds * (2 ** (source.consecutive_failures - 1)),
    )
    source.next_fetch_at = now + timedelta(seconds=backoff)


class SourceRegistry:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def register(self, registration: SourceRegistration) -> SourceSnapshot:
        with self._session_factory.begin() as session:
            source = Source(
                name=registration.name,
                kind=registration.kind.value,
                base_url=registration.base_url,
                enabled=registration.enabled,
                trust_tier=registration.trust_tier.value,
                default_evidence_tier=registration.default_evidence_tier.value,
                locale=registration.locale,
                vertical_keys=list(registration.vertical_keys),
                fetch_policy=registration.fetch_policy.model_dump(mode="json"),
                retention_days=registration.retention_days,
                redact_raw_content=registration.redact_raw_content,
                config=dict(registration.config),
                health_status=SourceHealthStatus.HEALTHY.value,
                consecutive_failures=0,
            )
            session.add(source)
            session.flush()
            return self._snapshot(source)

    def get(self, source_id: UUID) -> SourceSnapshot:
        with self._session_factory() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise LookupError(str(source_id))
            return self._snapshot(source)

    def eligible_sources(
        self,
        vertical_key: str,
        *,
        now: datetime | None = None,
    ) -> list[SourceSnapshot]:
        with self._session_factory() as session:
            sources = list(
                session.scalars(
                    select(Source)
                    .where(Source.enabled.is_(True))
                    .order_by(Source.name, Source.id)
                )
            )

        snapshots = [self._snapshot(source) for source in sources]
        return [
            source
            for source in snapshots
            if source.health_status is not SourceHealthStatus.PAUSED
            and (not source.vertical_keys or vertical_key in source.vertical_keys)
            and (now is None or source.next_fetch_at is None or source.next_fetch_at <= now)
        ]

    def mark_success(
        self,
        source_id: UUID,
        *,
        policy: FetchPolicy,
        now: datetime,
        cursor: str | None,
    ) -> None:
        with self._session_factory.begin() as session:
            source = self._locked_source(session, source_id)
            apply_source_success(
                source,
                policy=policy,
                now=now,
                cursor=cursor,
            )

    def mark_failure(
        self,
        source_id: UUID,
        *,
        policy: FetchPolicy,
        now: datetime,
        error_kind: str,
        retryable: bool,
    ) -> None:
        with self._session_factory.begin() as session:
            source = self._locked_source(session, source_id)
            apply_source_failure(
                source,
                policy=policy,
                now=now,
                error_kind=error_kind,
                retryable=retryable,
            )

    @staticmethod
    def _locked_source(session: Session, source_id: UUID) -> Source:
        source = session.scalar(
            select(Source).where(Source.id == source_id).with_for_update()
        )
        if source is None:
            raise LookupError(str(source_id))
        return source

    @staticmethod
    def _snapshot(source: Source) -> SourceSnapshot:
        return SourceSnapshot(
            id=source.id,
            name=source.name,
            kind=SourceKind(source.kind),
            base_url=source.base_url,
            enabled=source.enabled,
            trust_tier=EvidenceTier(source.trust_tier),
            default_evidence_tier=EvidenceTier(source.default_evidence_tier),
            locale=source.locale,
            vertical_keys=list(source.vertical_keys),
            fetch_policy=FetchPolicy.model_validate(source.fetch_policy or {}),
            retention_days=source.retention_days,
            redact_raw_content=source.redact_raw_content,
            config=dict(source.config),
            health_status=SourceHealthStatus(source.health_status),
            consecutive_failures=source.consecutive_failures,
            next_fetch_at=source.next_fetch_at,
            cursor=source.cursor,
        )
