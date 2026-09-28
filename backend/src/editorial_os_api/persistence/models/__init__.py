"""Canonical SQLAlchemy models.

Importing this module registers every table with Base.metadata for migrations/tests.
"""

from editorial_os_api.persistence.models.content import Asset, Draft, draft_claim_links
from editorial_os_api.persistence.models.delivery import (
    DistributionJob,
    PerformanceSnapshot,
    Publication,
)
from editorial_os_api.persistence.models.evidence import Claim, EvidenceItem, claim_evidence_links
from editorial_os_api.persistence.models.governance import AuditEvent, GateDecision
from editorial_os_api.persistence.models.model_usage import ModelUsageRecord
from editorial_os_api.persistence.models.source import Source, SourceItem
from editorial_os_api.persistence.models.workflow import (
    EditorialBrief,
    TopicCandidate,
    WorkflowAction,
    WorkflowRun,
    brief_claim_links,
)

__all__ = [
    "Asset",
    "AuditEvent",
    "Claim",
    "DistributionJob",
    "Draft",
    "EditorialBrief",
    "EvidenceItem",
    "GateDecision",
    "ModelUsageRecord",
    "PerformanceSnapshot",
    "Publication",
    "Source",
    "SourceItem",
    "TopicCandidate",
    "WorkflowAction",
    "WorkflowRun",
    "brief_claim_links",
    "claim_evidence_links",
    "draft_claim_links",
]
