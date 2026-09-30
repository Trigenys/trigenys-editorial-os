"""Canonical SQLAlchemy models.

Importing this module registers every table with Base.metadata for migrations/tests.
"""

from editorial_os_api.persistence.models.content import (
    Asset,
    AssetManifest,
    Draft,
    draft_claim_links,
)
from editorial_os_api.persistence.models.delivery import (
    DistributionJob,
    PerformanceSnapshot,
    Publication,
)
from editorial_os_api.persistence.models.evidence import (
    Claim,
    EvidenceItem,
    ResearchBrief,
    claim_evidence_links,
)
from editorial_os_api.persistence.models.governance import (
    AuditEvent,
    EditorialQAReview,
    GateDecision,
)
from editorial_os_api.persistence.models.model_usage import ModelUsageRecord
from editorial_os_api.persistence.models.source import Source, SourceFetch, SourceItem
from editorial_os_api.persistence.models.workflow import (
    EditorialBrief,
    TopicCandidate,
    WorkflowAction,
    WorkflowRun,
    brief_claim_links,
)

__all__ = [
    "Asset",
    "AssetManifest",
    "AuditEvent",
    "Claim",
    "DistributionJob",
    "Draft",
    "EditorialBrief",
    "EditorialQAReview",
    "EvidenceItem",
    "GateDecision",
    "ModelUsageRecord",
    "PerformanceSnapshot",
    "Publication",
    "ResearchBrief",
    "Source",
    "SourceFetch",
    "SourceItem",
    "TopicCandidate",
    "WorkflowAction",
    "WorkflowRun",
    "brief_claim_links",
    "claim_evidence_links",
    "draft_claim_links",
]
