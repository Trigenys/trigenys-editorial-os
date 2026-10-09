from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import EvidenceTier, SourceKind
from editorial_os_api.persistence.models import Source
from editorial_os_api.scout.contracts import FetchPolicy, SourceRegistration

INSIGHT_VERTICAL_KEY = "trigenys-insight"
NEWS_REGISTRY_ID = "insight-news-v1"


@dataclass(frozen=True)
class NewsSourceSpec:
    key: str
    region: str
    roles: tuple[str, ...]
    topics: tuple[str, ...]
    discovery_weight: int
    registration: SourceRegistration


def _source(
    *,
    key: str,
    name: str,
    url: str,
    locale: str,
    tier: EvidenceTier,
    region: str,
    roles: tuple[str, ...],
    topics: tuple[str, ...],
    discovery_weight: int,
    interval_seconds: int = 3600,
    collection_mode: str = "feed-preferred",
    kind: SourceKind = SourceKind.WEB,
    publisher_url: str | None = None,
) -> NewsSourceSpec:
    return NewsSourceSpec(
        key=key,
        region=region,
        roles=roles,
        topics=topics,
        discovery_weight=discovery_weight,
        registration=SourceRegistration(
            name=name,
            kind=kind,
            base_url=url,
            trust_tier=tier,
            default_evidence_tier=tier,
            locale=locale,
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=interval_seconds),
            retention_days=90,
            redact_raw_content=True,
            config={
                "registry_id": NEWS_REGISTRY_ID,
                "source_key": key,
                "region": region,
                "roles": list(roles),
                "topics": list(topics),
                "discovery_weight": discovery_weight,
                "collection_mode": collection_mode,
                "publisher_url": publisher_url or url,
                "store_full_text": False,
                "scrape_policy": "respect-robots-and-terms",
            },
        ),
    )


NEWS_SOURCES: tuple[NewsSourceSpec, ...] = (
    # Cameroon
    _source(
        key="ecomatin",
        name="EcoMatin",
        url="https://ecomatin.net/",
        locale="fr",
        tier=EvidenceTier.E3,
        region="cameroon",
        roles=("discovery", "verification", "context"),
        topics=("business", "finance", "economy", "energy", "telecoms"),
        discovery_weight=95,
        interval_seconds=1800,
        collection_mode="listing-page",
        publisher_url="https://ecomatin.net/",
    ),
    _source(
        key="digital-business-africa",
        name="Digital Business Africa",
        url="https://www.digitalbusiness.africa/",
        locale="fr",
        tier=EvidenceTier.E3,
        region="cameroon",
        roles=("discovery", "verification", "context"),
        topics=("technology", "telecoms", "digital-policy", "startups", "cybersecurity"),
        discovery_weight=98,
        interval_seconds=1800,
        collection_mode="listing-page",
        publisher_url="https://www.digitalbusiness.africa/",
    ),
    _source(
        key="journal-du-cameroun",
        name="Journal du Cameroun",
        url="https://www.journalducameroun.com/",
        locale="fr",
        tier=EvidenceTier.E2,
        region="cameroon",
        roles=("discovery", "context"),
        topics=("business", "public-policy", "technology", "economy"),
        discovery_weight=82,
        interval_seconds=1800,
    ),
    _source(
        key="actu-cameroun",
        name="Actu Cameroun",
        url="https://actucameroun.com/",
        locale="fr",
        tier=EvidenceTier.E2,
        region="cameroon",
        roles=("discovery",),
        topics=("breaking-news", "business", "public-policy", "technology"),
        discovery_weight=78,
        interval_seconds=1800,
    ),
    _source(
        key="cameroon-info-net",
        name="Cameroon-Info.Net",
        url="https://www.cameroon-info.net/",
        locale="fr",
        tier=EvidenceTier.E2,
        region="cameroon",
        roles=("discovery",),
        topics=("breaking-news", "business", "public-policy", "technology"),
        discovery_weight=72,
        interval_seconds=3600,
    ),
    _source(
        key="business-in-cameroon",
        name="Business in Cameroon",
        url="https://www.businessincameroon.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="cameroon",
        roles=("discovery", "verification", "context"),
        topics=("business", "finance", "economy", "energy", "telecoms", "regulation"),
        discovery_weight=94,
        interval_seconds=3600,
    ),
    _source(
        key="cameroon-tribune",
        name="Cameroon Tribune",
        url="https://www.cameroon-tribune.cm/",
        locale="fr",
        tier=EvidenceTier.E3,
        region="cameroon",
        roles=("discovery", "official-statement-context"),
        topics=("public-policy", "economy", "infrastructure", "technology"),
        discovery_weight=76,
        interval_seconds=3600,
    ),
    # Africa
    _source(
        key="techcabal",
        name="TechCabal",
        url="https://techcabal.com/feed/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "verification", "context"),
        topics=("technology", "startups", "fintech", "telecoms", "ai", "digital-policy"),
        discovery_weight=98,
        interval_seconds=1800,
        kind=SourceKind.RSS,
        publisher_url="https://techcabal.com/",
    ),
    _source(
        key="techpoint-africa",
        name="Techpoint Africa",
        url="https://techpoint.africa/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "verification", "context"),
        topics=("technology", "startups", "fintech", "ai", "business"),
        discovery_weight=95,
        interval_seconds=1800,
    ),
    _source(
        key="mybroadband",
        name="MyBroadband",
        url="https://mybroadband.co.za/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "verification", "context"),
        topics=("telecoms", "cloud", "cybersecurity", "infrastructure", "technology"),
        discovery_weight=94,
        interval_seconds=1800,
    ),
    _source(
        key="techcentral",
        name="TechCentral",
        url="https://techcentral.co.za/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "verification", "context"),
        topics=("telecoms", "cloud", "cybersecurity", "enterprise-tech", "regulation"),
        discovery_weight=92,
        interval_seconds=1800,
    ),
    _source(
        key="nairametrics",
        name="Nairametrics",
        url="https://nairametrics.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "verification", "context"),
        topics=("finance", "fintech", "business", "economy", "markets"),
        discovery_weight=93,
        interval_seconds=1800,
    ),
    _source(
        key="african-business",
        name="African Business",
        url="https://african.business/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "context"),
        topics=("business", "finance", "economy", "investment", "infrastructure"),
        discovery_weight=86,
        interval_seconds=3600,
    ),
    _source(
        key="disrupt-africa",
        name="Disrupt Africa",
        url="https://disruptafrica.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="africa",
        roles=("discovery", "context"),
        topics=("startups", "venture-capital", "fintech", "technology"),
        discovery_weight=89,
        interval_seconds=3600,
    ),
    _source(
        key="rest-of-world",
        name="Rest of World",
        url="https://restofworld.org/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global-emerging-markets",
        roles=("discovery", "verification", "context"),
        topics=("technology", "ai", "platforms", "digital-work", "emerging-markets"),
        discovery_weight=96,
        interval_seconds=3600,
    ),
    # Global
    _source(
        key="reuters",
        name="Reuters",
        url="https://www.reuters.com/arc/outboundfeeds/news-sitemap-index/?outputType=xml",
        locale="en",
        tier=EvidenceTier.E4,
        region="global",
        roles=("discovery", "verification"),
        topics=("business", "technology", "markets", "telecoms", "ai", "cybersecurity"),
        discovery_weight=100,
        interval_seconds=1800,
        collection_mode="news-sitemap",
        publisher_url="https://www.reuters.com/",
    ),
    _source(
        key="bloomberg",
        name="Bloomberg",
        url="https://www.bloomberg.com/",
        locale="en",
        tier=EvidenceTier.E4,
        region="global",
        roles=("discovery", "verification", "context"),
        topics=("markets", "business", "technology", "ai", "finance"),
        discovery_weight=98,
        interval_seconds=1800,
        collection_mode="metadata-preferred",
    ),
    _source(
        key="wired",
        name="WIRED",
        url="https://www.wired.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "verification", "context"),
        topics=("technology", "ai", "cybersecurity", "science", "platforms"),
        discovery_weight=94,
        interval_seconds=1800,
    ),
    _source(
        key="techcrunch",
        name="TechCrunch",
        url="https://techcrunch.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "context"),
        topics=("startups", "venture-capital", "ai", "technology", "platforms"),
        discovery_weight=93,
        interval_seconds=1800,
    ),
    _source(
        key="the-verge",
        name="The Verge",
        url="https://www.theverge.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "context"),
        topics=("technology", "ai", "consumer-tech", "platforms", "hardware"),
        discovery_weight=90,
        interval_seconds=1800,
    ),
    _source(
        key="ars-technica",
        name="Ars Technica",
        url="https://arstechnica.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "verification", "context"),
        topics=("cloud", "cybersecurity", "ai", "software", "infrastructure"),
        discovery_weight=94,
        interval_seconds=1800,
    ),
    _source(
        key="bleeping-computer",
        name="BleepingComputer",
        url="https://www.bleepingcomputer.com/feed/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "verification"),
        topics=("cybersecurity", "ransomware", "vulnerabilities", "incident-response"),
        discovery_weight=97,
        interval_seconds=900,
        kind=SourceKind.RSS,
        publisher_url="https://www.bleepingcomputer.com/",
    ),
    _source(
        key="krebs-on-security",
        name="KrebsOnSecurity",
        url="https://krebsonsecurity.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "verification", "context"),
        topics=("cybersecurity", "fraud", "threat-actors", "incident-response"),
        discovery_weight=95,
        interval_seconds=3600,
    ),
    _source(
        key="dark-reading",
        name="Dark Reading",
        url="https://www.darkreading.com/",
        locale="en",
        tier=EvidenceTier.E3,
        region="global",
        roles=("discovery", "verification", "context"),
        topics=("cybersecurity", "enterprise-security", "cloud-security", "vulnerabilities"),
        discovery_weight=91,
        interval_seconds=1800,
    ),
)


def seed_news_sources(
    session_factory: sessionmaker[Session],
) -> dict[str, UUID]:
    """Create or reconcile the Trigenys Insight News Scout registry."""

    ids: dict[str, UUID] = {}
    with session_factory.begin() as session:
        existing = list(
            session.scalars(
                select(Source).where(
                    Source.vertical_keys.contains([INSIGHT_VERTICAL_KEY])
                )
            )
        )
        by_key = {
            str(source.config.get("source_key")): source
            for source in existing
            if source.config.get("registry_id") == NEWS_REGISTRY_ID
            and source.config.get("source_key")
        }

        for spec in NEWS_SOURCES:
            registration = spec.registration
            source = by_key.get(spec.key)
            if source is None:
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
                    health_status="HEALTHY",
                    consecutive_failures=0,
                )
                session.add(source)
                session.flush()
            else:
                source.name = registration.name
                source.kind = registration.kind.value
                source.base_url = registration.base_url
                source.enabled = registration.enabled
                source.trust_tier = registration.trust_tier.value
                source.default_evidence_tier = (
                    registration.default_evidence_tier.value
                )
                source.locale = registration.locale
                source.vertical_keys = list(registration.vertical_keys)
                source.fetch_policy = registration.fetch_policy.model_dump(mode="json")
                source.retention_days = registration.retention_days
                source.redact_raw_content = registration.redact_raw_content
                source.config = dict(registration.config)
            ids[spec.key] = source.id

    return ids
