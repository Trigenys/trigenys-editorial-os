from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import ConfidenceClass, RiskClass, WorkflowStatus
from editorial_os_api.editorial_intelligence import EditorialIntelligenceAgent
from editorial_os_api.editorial_intelligence.contracts import (
    DecisionThresholds,
    EditorialIntelligenceResult,
    SignalDocument,
    VerticalIntelligencePolicy,
)
from editorial_os_api.editorial_intelligence.scoring import (
    cluster_documents,
    cluster_key,
)
from editorial_os_api.persistence.models import Source, SourceItem, WorkflowRun
from editorial_os_api.scout.news_registry import NEWS_REGISTRY_ID

NEWS_RADAR_VERTICAL_VERSION = "2026.10-pilot.1"


def insight_news_policy() -> VerticalIntelligencePolicy:
    return VerticalIntelligencePolicy(
        vertical_key="trigenys-insight",
        version=NEWS_RADAR_VERTICAL_VERSION,
        eligible_locales=["fr", "en"],
        priority_terms=[
            "ai",
            "intelligence artificielle",
            "cloud",
            "cybersecurity",
            "cybersécurité",
            "telecom",
            "télécom",
            "fintech",
            "startup",
            "digital",
            "numérique",
            "data center",
            "datacenter",
            "e-commerce",
            "paiement",
            "payments",
            "mobile money",
            "infrastructure",
            "software",
            "internet",
            "5g",
            "satellite",
        ],
        supported_formats=["article", "brief", "analysis"],
        default_format="article",
        cluster_similarity_threshold=0.35,
        thresholds=DecisionThresholds(
            propose_min=70,
            watch_min=45,
            stale_after_hours=72,
            novelty_window_hours=24 * 7,
        ),
        use_model_strategy=False,
    )


class NewsRadarService:
    """Promote recent News Scout signals into idempotent editorial candidates."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def promote_recent(
        self,
        *,
        now: datetime | None = None,
        lookback_hours: int = 24,
        max_clusters: int = 8,
    ) -> dict[str, Any]:
        observed_now = now or datetime.now(UTC)
        cutoff = observed_now - timedelta(hours=lookback_hours)
        policy = insight_news_policy()

        with self._session_factory() as session:
            rows = list(
                session.execute(
                    select(SourceItem, Source)
                    .join(Source, Source.id == SourceItem.source_id)
                    .where(
                        Source.config["registry_id"].astext == NEWS_REGISTRY_ID,
                        Source.enabled.is_(True),
                        SourceItem.observed_at >= cutoff,
                    )
                    .order_by(SourceItem.observed_at.desc())
                )
            )

        documents = [
            SignalDocument(
                id=item.id,
                source_id=item.source_id,
                title=item.title or item.canonical_url,
                summary=self._summary(item),
                locale=item.locale or source.locale,
                published_at_iso=(
                    item.published_at.isoformat()
                    if item.published_at is not None
                    else None
                ),
                observed_at_iso=item.observed_at.isoformat(),
            )
            for item, source in rows
            if (item.locale or source.locale) in policy.eligible_locales
        ]

        if not documents:
            return {
                "signals": 0,
                "clusters": 0,
                "created_runs": 0,
                "results": [],
            }

        clusters = cluster_documents(
            documents,
            threshold=policy.cluster_similarity_threshold,
        )
        clusters.sort(
            key=lambda group: (
                -len(group),
                -max(
                    datetime.fromisoformat(
                        document.published_at_iso or document.observed_at_iso
                    ).timestamp()
                    for document in group
                ),
                cluster_key(group),
            )
        )

        results: list[dict[str, Any]] = []
        created_runs = 0
        agent = EditorialIntelligenceAgent(self._session_factory)

        for group in clusters[:max_clusters]:
            key = cluster_key(group)
            week = observed_now.strftime("%G-W%V")
            idempotency_key = f"news-radar:{week}:{key}"

            with self._session_factory.begin() as session:
                run = session.scalar(
                    select(WorkflowRun).where(
                        WorkflowRun.idempotency_key == idempotency_key
                    )
                )
                if run is None:
                    run = WorkflowRun(
                        vertical_key=policy.vertical_key,
                        vertical_version=policy.version,
                        status=WorkflowStatus.INGESTED.value,
                        risk_class=RiskClass.R0.value,
                        confidence_class=ConfidenceClass.C0.value,
                        policy_version=policy.version,
                        idempotency_key=idempotency_key,
                        context={
                            "origin": "news-radar",
                            "registry_id": NEWS_REGISTRY_ID,
                            "cluster_key": key,
                            "source_item_ids": [
                                str(document.id) for document in group
                            ],
                        },
                    )
                    session.add(run)
                    session.flush()
                    created_runs += 1
                workflow_run_id = run.id

            result = agent.analyze(
                workflow_run_id,
                [document.id for document in group],
                policy=policy,
                now=observed_now,
            )
            results.append(self._serialize(result))

        return {
            "signals": len(documents),
            "clusters": len(clusters),
            "created_runs": created_runs,
            "results": results,
        }

    @staticmethod
    def _summary(item: SourceItem) -> str:
        value = item.extracted_payload.get("summary")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _serialize(result: EditorialIntelligenceResult) -> dict[str, Any]:
        return {
            "workflow_run_id": str(result.workflow_run_id),
            "candidate_id": str(result.candidate_id),
            "decision": result.decision.value,
            "title_cluster": result.cluster_key,
            "composite_score": result.composite_score,
            "pending_gate": result.pending_gate,
            "source_item_ids": [str(value) for value in result.source_item_ids],
        }
