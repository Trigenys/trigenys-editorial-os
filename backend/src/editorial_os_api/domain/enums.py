from enum import StrEnum


class EvidenceTier(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


class ConfidenceClass(StrEnum):
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class WorkflowStatus(StrEnum):
    INGESTED = "INGESTED"
    CANDIDATE = "CANDIDATE"
    TOPIC_APPROVED = "TOPIC_APPROVED"
    VERIFIED = "VERIFIED"
    DRAFTED = "DRAFTED"
    ASSETS_READY = "ASSETS_READY"
    QA_PASSED = "QA_PASSED"
    EDITORIAL_APPROVED = "EDITORIAL_APPROVED"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISH_APPROVED = "PUBLISH_APPROVED"
    PUBLISHED = "PUBLISHED"
    DISTRIBUTED = "DISTRIBUTED"
    MEASURED = "MEASURED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class TopicDecision(StrEnum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    PROPOSE = "PROPOSE"


class GateKind(StrEnum):
    TOPIC = "A"
    EDITORIAL = "B"
    PUBLISH = "C"


class GateOutcome(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    WATCH = "WATCH"


class AssetKind(StrEnum):
    IMAGE = "IMAGE"
    INFOGRAPHIC = "INFOGRAPHIC"
    VIDEO = "VIDEO"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class PublicationStatus(StrEnum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class DistributionStatus(StrEnum):
    PREVIEW = "PREVIEW"
    SCHEDULED = "SCHEDULED"
    POSTED = "POSTED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class AuditActorKind(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"
