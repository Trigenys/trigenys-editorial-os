from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import EvidenceTier, RiskClass, SourceKind
from editorial_os_api.persistence.models import Source
from editorial_os_api.scout.contracts import FetchPolicy, SourceRegistration

INSIGHT_PILOT_ID = "insight-e2e-2026-10"
INSIGHT_VERTICAL_KEY = "trigenys-insight"
INSIGHT_VERTICAL_VERSION = "2026.10-pilot.1"


@dataclass(frozen=True)
class ApprovedSourceSpec:
    key: str
    registration: SourceRegistration


@dataclass(frozen=True)
class PilotScenario:
    key: str
    title: str
    locale: str
    content_format: str
    risk_class: RiskClass
    source_keys: tuple[str, ...]
    tags: tuple[str, ...]


APPROVED_SOURCES: tuple[ApprovedSourceSpec, ...] = (
    ApprovedSourceSpec(
        key="minpostel",
        registration=SourceRegistration(
            name="MINPOSTEL Cameroon",
            kind=SourceKind.WEB,
            base_url="https://www.minpostel.gov.cm/",
            trust_tier=EvidenceTier.E4,
            default_evidence_tier=EvidenceTier.E4,
            locale="fr",
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=3600),
            retention_days=180,
            redact_raw_content=True,
            config={
                "pilot_id": INSIGHT_PILOT_ID,
                "source_key": "minpostel",
                "role": "primary-official",
            },
        ),
    ),
    ApprovedSourceSpec(
        key="art-cameroon",
        registration=SourceRegistration(
            name="ART Cameroon",
            kind=SourceKind.WEB,
            base_url="https://www.art.cm/",
            trust_tier=EvidenceTier.E4,
            default_evidence_tier=EvidenceTier.E4,
            locale="fr",
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=3600),
            retention_days=180,
            redact_raw_content=True,
            config={
                "pilot_id": INSIGHT_PILOT_ID,
                "source_key": "art-cameroon",
                "role": "primary-regulator",
            },
        ),
    ),
    ApprovedSourceSpec(
        key="ins-cameroon",
        registration=SourceRegistration(
            name="Institut National de la Statistique Cameroun",
            kind=SourceKind.WEB,
            base_url="https://ins-cameroun.cm/",
            trust_tier=EvidenceTier.E4,
            default_evidence_tier=EvidenceTier.E4,
            locale="fr",
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=21_600),
            retention_days=365,
            redact_raw_content=True,
            config={
                "pilot_id": INSIGHT_PILOT_ID,
                "source_key": "ins-cameroon",
                "role": "primary-statistics",
            },
        ),
    ),
    ApprovedSourceSpec(
        key="world-bank-cameroon",
        registration=SourceRegistration(
            name="World Bank Cameroon",
            kind=SourceKind.WEB,
            base_url="https://www.worldbank.org/en/country/cameroon",
            trust_tier=EvidenceTier.E4,
            default_evidence_tier=EvidenceTier.E4,
            locale="en",
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=21_600),
            retention_days=365,
            redact_raw_content=True,
            config={
                "pilot_id": INSIGHT_PILOT_ID,
                "source_key": "world-bank-cameroon",
                "role": "primary-development-data",
            },
        ),
    ),
    ApprovedSourceSpec(
        key="ifc-africa",
        registration=SourceRegistration(
            name="IFC Africa",
            kind=SourceKind.WEB,
            base_url="https://www.ifc.org/en/where-we-work/africa",
            trust_tier=EvidenceTier.E4,
            default_evidence_tier=EvidenceTier.E4,
            locale="en",
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=21_600),
            retention_days=365,
            redact_raw_content=True,
            config={
                "pilot_id": INSIGHT_PILOT_ID,
                "source_key": "ifc-africa",
                "role": "primary-investment",
            },
        ),
    ),
    ApprovedSourceSpec(
        key="gsma",
        registration=SourceRegistration(
            name="GSMA",
            kind=SourceKind.WEB,
            base_url="https://www.gsma.com/",
            trust_tier=EvidenceTier.E3,
            default_evidence_tier=EvidenceTier.E3,
            locale="en",
            vertical_keys=[INSIGHT_VERTICAL_KEY],
            fetch_policy=FetchPolicy(interval_seconds=21_600),
            retention_days=180,
            redact_raw_content=True,
            config={
                "pilot_id": INSIGHT_PILOT_ID,
                "source_key": "gsma",
                "role": "industry-research",
            },
        ),
    ),
)


PILOT_SCENARIOS: tuple[PilotScenario, ...] = (
    PilotScenario(
        key="digital-infrastructure-douala",
        title="What a new data-center investment changes for digital services in Douala",
        locale="fr",
        content_format="analysis",
        risk_class=RiskClass.R1,
        source_keys=("minpostel", "art-cameroon", "world-bank-cameroon"),
        tags=("infrastructure", "cloud", "cameroon"),
    ),
    PilotScenario(
        key="qr-code-cameroon",
        title="QR codes in Cameroon: useful standard, bad implementation, or both?",
        locale="fr",
        content_format="article",
        risk_class=RiskClass.R0,
        source_keys=("art-cameroon", "gsma"),
        tags=("payments", "consumer-tech", "cameroon"),
    ),
    PilotScenario(
        key="african-ai-learning",
        title="Why African teams should learn AI systems, not only prompt syntax",
        locale="fr",
        content_format="analysis",
        risk_class=RiskClass.R1,
        source_keys=("world-bank-cameroon", "ifc-africa"),
        tags=("ai", "skills", "africa"),
    ),
    PilotScenario(
        key="startup-financing",
        title="Where startup financing actually comes from in Cameroon and Africa",
        locale="fr",
        content_format="analysis",
        risk_class=RiskClass.R2,
        source_keys=("ifc-africa", "world-bank-cameroon", "ins-cameroon"),
        tags=("startups", "finance", "africa"),
    ),
    PilotScenario(
        key="ecommerce-local-market",
        title="What local e-commerce operators reveal about trust and logistics",
        locale="fr",
        content_format="article",
        risk_class=RiskClass.R1,
        source_keys=("ins-cameroon", "world-bank-cameroon"),
        tags=("ecommerce", "logistics", "cameroon"),
    ),
    PilotScenario(
        key="cybersecurity-small-business",
        title="The practical cybersecurity baseline small African businesses can afford",
        locale="en",
        content_format="brief",
        risk_class=RiskClass.R1,
        source_keys=("gsma", "ifc-africa"),
        tags=("cybersecurity", "sme", "africa"),
    ),
    PilotScenario(
        key="cloud-local-business",
        title="Cloud does not mean one architecture: what local businesses should compare",
        locale="fr",
        content_format="analysis",
        risk_class=RiskClass.R1,
        source_keys=("world-bank-cameroon", "gsma"),
        tags=("cloud", "architecture", "cameroon"),
    ),
    PilotScenario(
        key="offline-low-bandwidth",
        title="Designing useful digital services for offline and 2G constraints",
        locale="fr",
        content_format="article",
        risk_class=RiskClass.R0,
        source_keys=("gsma", "art-cameroon"),
        tags=("offline", "2g", "product"),
    ),
    PilotScenario(
        key="gaming-digital-work",
        title="Professional gaming as digital work: what the African market still lacks",
        locale="fr",
        content_format="article",
        risk_class=RiskClass.R1,
        source_keys=("world-bank-cameroon", "ifc-africa"),
        tags=("gaming", "digital-work", "africa"),
    ),
    PilotScenario(
        key="mobile-economy-cameroon",
        title="What mobile-economy indicators can and cannot tell us about Cameroon",
        locale="en",
        content_format="analysis",
        risk_class=RiskClass.R1,
        source_keys=("gsma", "art-cameroon", "ins-cameroon"),
        tags=("mobile", "data-literacy", "cameroon"),
    ),
)


def seed_approved_sources(
    session_factory: sessionmaker[Session],
) -> dict[str, UUID]:
    """Create or reconcile the approved pilot source set without duplicates."""
    ids: dict[str, UUID] = {}
    with session_factory.begin() as session:
        existing_sources = list(
            session.scalars(
                select(Source).where(
                    Source.vertical_keys.contains([INSIGHT_VERTICAL_KEY])
                )
            )
        )
        by_key = {
            str(source.config.get("source_key")): source
            for source in existing_sources
            if source.config.get("pilot_id") == INSIGHT_PILOT_ID
            and source.config.get("source_key")
        }

        for spec in APPROVED_SOURCES:
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
