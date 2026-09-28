import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    SourceFailureKind,
    SourceFetchStatus,
    SourceHealthStatus,
)
from editorial_os_api.observability import ObservabilityHub, ProductTelemetryEvent
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import Source, SourceFetch, SourceItem
from editorial_os_api.scout.contracts import (
    ManualUrlInput,
    NormalizedSourceItem,
    RawFetchBatch,
    RawSourceItem,
    ScoutIngestResult,
    SourceAdapter,
)
from editorial_os_api.scout.errors import SourceAdapterError
from editorial_os_api.scout.normalize import (
    canonicalize_url,
    content_fingerprint,
    identity_key,
    normalized_text,
)
from editorial_os_api.scout.registry import SourceRegistry


class ScoutAgent:
    """Deterministic ingestion agent. It never creates editorial angles or workflow state."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        observability: ObservabilityHub | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = SourceRegistry(session_factory)
        self._observability = observability or ObservabilityHub()

    def ingest(
        self,
        source_id: UUID,
        adapter: SourceAdapter,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> ScoutIngestResult:
        observed_at = now or utcnow()
        source = self._registry.get(source_id)

        if not source.enabled:
            return ScoutIngestResult(
                source_id=source_id,
                status="SKIPPED",
                skipped_reason="disabled",
            )
        if source.health_status is SourceHealthStatus.PAUSED and not force:
            return ScoutIngestResult(
                source_id=source_id,
                status="SKIPPED",
                skipped_reason="paused",
            )
        if (
            source.next_fetch_at is not None
            and source.next_fetch_at > observed_at
            and not force
        ):
            return ScoutIngestResult(
                source_id=source_id,
                status="SKIPPED",
                skipped_reason="backoff",
            )

        try:
            requested_url = adapter.requested_url(source)
            batch = adapter.fetch(source)
        except SourceAdapterError as exc:
            return self._record_failure(
                source_id=source_id,
                adapter_name=adapter.name,
                requested_url=self._safe_requested_url(adapter, source),
                observed_at=observed_at,
                error=exc,
            )
        except Exception as exc:
            wrapped = SourceAdapterError(
                f"Unexpected source adapter failure: {type(exc).__name__}.",
                kind=SourceFailureKind.UNKNOWN,
                retryable=True,
            )
            return self._record_failure(
                source_id=source_id,
                adapter_name=adapter.name,
                requested_url=self._safe_requested_url(adapter, source),
                observed_at=observed_at,
                error=wrapped,
            )

        return self._persist_success(
            source_id=source_id,
            source_snapshot=source,
            batch=batch,
            requested_url=requested_url,
            observed_at=observed_at,
        )

    def ingest_manual_url(
        self,
        source_id: UUID,
        manual: ManualUrlInput,
        *,
        extractor: object,
        force: bool = True,
        now: datetime | None = None,
    ) -> ScoutIngestResult:
        from editorial_os_api.scout.adapters.manual import ManualUrlAdapter
        from editorial_os_api.scout.contracts import PageExtractor

        if not hasattr(extractor, "extract") or not hasattr(extractor, "name"):
            raise TypeError("extractor must satisfy the PageExtractor contract.")
        typed_extractor = extractor
        assert isinstance(typed_extractor, PageExtractor.__constraints__ if False else object)
        adapter = ManualUrlAdapter(
            str(manual.url),
            typed_extractor,  # type: ignore[arg-type]
            title=manual.title,
            locale=manual.locale,
        )
        return self.ingest(source_id, adapter, force=force, now=now)

    def _persist_success(
        self,
        *,
        source_id: UUID,
        source_snapshot: object,
        batch: RawFetchBatch,
        requested_url: str,
        observed_at: datetime,
    ) -> ScoutIngestResult:
        from editorial_os_api.scout.contracts import SourceSnapshot

        assert isinstance(source_snapshot, SourceSnapshot)
        raw_sha256 = (
            hashlib.sha256(batch.raw_payload.encode()).hexdigest()
            if batch.raw_payload is not None
            else None
        )

        created_count = 0
        updated_count = 0
        with self._session_factory.begin() as session:
            source = self._locked_source(session, source_id)
            fetch = SourceFetch(
                source_id=source_id,
                adapter=batch.adapter,
                requested_url=requested_url,
                status=SourceFetchStatus.SUCCEEDED.value,
                failure_kind=None,
                retryable=None,
                started_at=observed_at,
                completed_at=utcnow(),
                http_status=batch.http_status,
                content_type=batch.content_type,
                raw_payload=None if source.redact_raw_content else batch.raw_payload,
                raw_sha256=raw_sha256,
                metadata_=dict(batch.metadata),
                error_message=None,
            )
            session.add(fetch)
            session.flush()

            for raw_item in batch.items:
                normalized = self._normalize_item(
                    source_snapshot,
                    fetch.id,
                    raw_item,
                    batch,
                    observed_at,
                )
                existing = self._find_existing_item(session, normalized)
                if existing is None:
                    session.add(
                        SourceItem(
                            source_id=normalized.source_id,
                            source_fetch_id=normalized.source_fetch_id,
                            external_id=normalized.external_id,
                            identity_key=normalized.identity_key,
                            canonical_url=normalized.canonical_url,
                            title=normalized.title,
                            content_hash=normalized.content_hash,
                            locale=normalized.locale,
                            raw_content=None,
                            extracted_payload=dict(normalized.extracted_payload),
                            provenance=dict(normalized.provenance),
                            published_at=normalized.published_at,
                            observed_at=normalized.observed_at,
                            retain_until=self._retain_until(source, observed_at),
                            redacted_at=None,
                        )
                    )
                    created_count += 1
                else:
                    existing.source_fetch_id = normalized.source_fetch_id
                    existing.external_id = normalized.external_id
                    existing.canonical_url = normalized.canonical_url
                    existing.title = normalized.title
                    existing.content_hash = normalized.content_hash
                    existing.locale = normalized.locale
                    existing.raw_content = None
                    existing.extracted_payload = dict(normalized.extracted_payload)
                    existing.provenance = dict(normalized.provenance)
                    existing.published_at = normalized.published_at
                    existing.observed_at = normalized.observed_at
                    existing.retain_until = self._retain_until(source, observed_at)
                    updated_count += 1

            source.health_status = SourceHealthStatus.HEALTHY.value
            source.consecutive_failures = 0
            source.last_success_at = observed_at
            source.last_error_kind = None
            source.next_fetch_at = observed_at + timedelta(
                seconds=source_snapshot.fetch_policy.interval_seconds
            )
            if batch.cursor is not None:
                source.cursor = batch.cursor

            fetch_id = fetch.id

        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="source ingest succeeded",
                agent_id="scout",
                properties={
                    "source_id": str(source_id),
                    "adapter": batch.adapter,
                    "fetch_id": str(fetch_id),
                    "created_count": created_count,
                    "updated_count": updated_count,
                },
            )
        )
        return ScoutIngestResult(
            source_id=source_id,
            fetch_id=fetch_id,
            status="SUCCEEDED",
            created_count=created_count,
            updated_count=updated_count,
        )

    def _record_failure(
        self,
        *,
        source_id: UUID,
        adapter_name: str,
        requested_url: str,
        observed_at: datetime,
        error: SourceAdapterError,
    ) -> ScoutIngestResult:
        with self._session_factory.begin() as session:
            source = self._locked_source(session, source_id)
            policy = self._registry._snapshot(source).fetch_policy
            fetch = SourceFetch(
                source_id=source_id,
                adapter=adapter_name,
                requested_url=requested_url,
                status=SourceFetchStatus.FAILED.value,
                failure_kind=error.kind.value,
                retryable=error.retryable,
                started_at=observed_at,
                completed_at=utcnow(),
                http_status=error.http_status,
                content_type=None,
                raw_payload=None,
                raw_sha256=None,
                metadata_={},
                error_message=str(error)[:2000],
            )
            session.add(fetch)
            session.flush()

            source.consecutive_failures += 1
            source.last_failure_at = observed_at
            source.last_error_kind = error.kind.value
            should_pause = (
                not error.retryable
                or source.consecutive_failures >= policy.max_failures_before_pause
            )
            if should_pause:
                source.health_status = SourceHealthStatus.PAUSED.value
                source.next_fetch_at = None
            else:
                source.health_status = SourceHealthStatus.DEGRADED.value
                backoff = min(
                    policy.max_backoff_seconds,
                    policy.interval_seconds * (2 ** (source.consecutive_failures - 1)),
                )
                source.next_fetch_at = observed_at + timedelta(seconds=backoff)
            fetch_id = fetch.id

        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="source ingest failed",
                agent_id="scout",
                properties={
                    "source_id": str(source_id),
                    "adapter": adapter_name,
                    "fetch_id": str(fetch_id),
                    "failure_kind": error.kind.value,
                    "retryable": error.retryable,
                },
            )
        )
        return ScoutIngestResult(
            source_id=source_id,
            fetch_id=fetch_id,
            status="FAILED",
            failure_kind=error.kind.value,
            retryable=error.retryable,
        )

    @staticmethod
    def _normalize_item(
        source: object,
        fetch_id: UUID,
        raw_item: RawSourceItem,
        batch: RawFetchBatch,
        observed_at: datetime,
    ) -> NormalizedSourceItem:
        from editorial_os_api.scout.contracts import SourceSnapshot

        assert isinstance(source, SourceSnapshot)
        canonical_url = canonicalize_url(raw_item.url)
        return NormalizedSourceItem(
            source_id=source.id,
            source_fetch_id=fetch_id,
            external_id=normalized_text(raw_item.external_id) or None,
            identity_key=identity_key(
                source.id,
                external_id=raw_item.external_id,
                canonical_url=canonical_url,
            ),
            canonical_url=canonical_url,
            title=normalized_text(raw_item.title) or None,
            content_hash=content_fingerprint(raw_item, canonical_url),
            locale=raw_item.locale or source.locale,
            extracted_payload={
                "body": normalized_text(raw_item.body) or None,
                "summary": normalized_text(raw_item.summary) or None,
                "payload": dict(raw_item.payload),
            },
            provenance={
                "source_id": str(source.id),
                "source_fetch_id": str(fetch_id),
                "adapter": batch.adapter,
                "requested_url": batch.requested_url,
                "trust_tier": source.trust_tier.value,
                "evidence_tier": source.default_evidence_tier.value,
                "observed_at": observed_at.isoformat(),
            },
            published_at=raw_item.published_at,
            observed_at=observed_at,
        )

    @staticmethod
    def _find_existing_item(
        session: Session,
        normalized: NormalizedSourceItem,
    ) -> SourceItem | None:
        existing = session.scalar(
            select(SourceItem).where(
                SourceItem.source_id == normalized.source_id,
                SourceItem.identity_key == normalized.identity_key,
            )
        )
        if existing is not None:
            return existing

        if normalized.external_id is not None:
            existing = session.scalar(
                select(SourceItem).where(
                    SourceItem.source_id == normalized.source_id,
                    SourceItem.external_id == normalized.external_id,
                )
            )
            if existing is not None:
                return existing

        return session.scalar(
            select(SourceItem).where(
                SourceItem.source_id == normalized.source_id,
                SourceItem.content_hash == normalized.content_hash,
            )
        )

    @staticmethod
    def _retain_until(source: Source, observed_at: datetime) -> datetime | None:
        if source.retention_days is None:
            return None
        return observed_at + timedelta(days=source.retention_days)

    @staticmethod
    def _locked_source(session: Session, source_id: UUID) -> Source:
        source = session.scalar(
            select(Source).where(Source.id == source_id).with_for_update()
        )
        if source is None:
            raise LookupError(str(source_id))
        return source

    @staticmethod
    def _safe_requested_url(adapter: SourceAdapter, source: object) -> str:
        from editorial_os_api.scout.contracts import SourceSnapshot

        assert isinstance(source, SourceSnapshot)
        try:
            return adapter.requested_url(source)
        except Exception:
            return source.base_url or f"{source.kind.value.lower()}://{source.id}"
