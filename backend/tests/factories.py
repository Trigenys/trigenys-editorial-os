from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.orm import Session

from editorial_os_api.persistence.models import (
    Asset,
    AuditEvent,
    Claim,
    DistributionJob,
    Draft,
    EditorialBrief,
    EvidenceItem,
    GateDecision,
    PerformanceSnapshot,
    Publication,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowRun,
    brief_claim_links,
    claim_evidence_links,
    draft_claim_links,
)


@dataclass(frozen=True)
class CompleteWorkflowFixture:
    source: Source
    source_item: SourceItem
    workflow: WorkflowRun
    topic: TopicCandidate
    evidence: EvidenceItem
    claim: Claim
    brief: EditorialBrief
    draft: Draft
    asset: Asset
    topic_gate: GateDecision
    editorial_gate: GateDecision
    publish_gate: GateDecision
    audit_event: AuditEvent
    publication: Publication
    distribution: DistributionJob
    performance: PerformanceSnapshot


def create_complete_workflow(session: Session, *, suffix: str) -> CompleteWorkflowFixture:
    now = datetime.now(UTC)

    source = Source(
        name=f"Fixture Source {suffix}",
        kind="official",
        base_url="https://example.test",
        enabled=True,
        default_evidence_tier="E3",
        retention_days=30,
        redact_raw_content=True,
        config={"fixture": True},
    )
    session.add(source)
    session.flush()

    source_item = SourceItem(
        source_id=source.id,
        external_id=f"item-{suffix}",
        canonical_url=f"https://example.test/items/{suffix}",
        title="Fixture signal",
        content_hash=f"sha256-{suffix}",
        raw_content="Fixture source body",
        extracted_payload={"summary": "Fixture signal"},
        published_at=now,
        observed_at=now,
        retain_until=None,
        redacted_at=None,
    )
    workflow = WorkflowRun(
        vertical_key="fixture",
        vertical_version="1",
        status="PUBLISHED",
        risk_class="R0",
        confidence_class="C4",
        policy_version="1",
        idempotency_key=f"workflow-{suffix}",
        context={"fixture": True},
    )
    session.add_all([source_item, workflow])
    session.flush()

    topic = TopicCandidate(
        workflow_run_id=workflow.id,
        title="Fixture topic",
        proposed_angle="Fixture angle",
        decision="PROPOSE",
        risk_class="R0",
        confidence_class="C4",
        reason_codes=["fixture"],
    )
    evidence = EvidenceItem(
        workflow_run_id=workflow.id,
        source_item_id=source_item.id,
        url=source_item.canonical_url,
        excerpt="Fixture evidence",
        tier="E3",
        observed_at=now,
        published_at=now,
        retain_until=None,
        redacted_at=None,
    )
    claim = Claim(
        workflow_run_id=workflow.id,
        statement="The fixture source published a fixture signal.",
        material=True,
        confidence_class="C4",
        risk_class="R0",
        contested=False,
    )
    session.add_all([topic, evidence, claim])
    session.flush()
    session.execute(
        insert(claim_evidence_links).values(
            claim_id=claim.id,
            evidence_item_id=evidence.id,
        )
    )

    brief = EditorialBrief(
        workflow_run_id=workflow.id,
        version=1,
        angle="Explain the verified fixture signal.",
        locale="en",
        instructions={"tone": "clear"},
    )
    session.add(brief)
    session.flush()
    session.execute(
        insert(brief_claim_links).values(
            editorial_brief_id=brief.id,
            claim_id=claim.id,
        )
    )

    draft = Draft(
        workflow_run_id=workflow.id,
        editorial_brief_id=brief.id,
        version=1,
        locale="en",
        title="Fixture article",
        deck="Fixture deck",
        body="The fixture source published a fixture signal.",
        metadata_payload={"seo_title": "Fixture article"},
    )
    session.add(draft)
    session.flush()
    session.execute(
        insert(draft_claim_links).values(
            draft_id=draft.id,
            claim_id=claim.id,
            support_status="SUPPORTED",
        )
    )

    asset = Asset(
        workflow_run_id=workflow.id,
        version=1,
        kind="IMAGE",
        uri="https://assets.example.test/fixture.webp",
        alt_text="Fixture editorial visual",
        caption="Fixture visual",
        provenance={"kind": "generated", "fixture": True},
        owner_key=f"asset-{suffix}",
    )
    session.add(asset)
    session.flush()

    topic_gate = GateDecision(
        workflow_run_id=workflow.id,
        gate="A",
        outcome="APPROVED",
        artifact_type="topic_candidate",
        artifact_id=topic.id,
        artifact_version=1,
        actor_id="fixture-operator",
        reason=None,
        decided_at=now,
        policy_version="1",
        details={},
    )
    editorial_gate = GateDecision(
        workflow_run_id=workflow.id,
        gate="B",
        outcome="APPROVED",
        artifact_type="draft",
        artifact_id=draft.id,
        artifact_version=draft.version,
        actor_id="fixture-operator",
        reason=None,
        decided_at=now,
        policy_version="1",
        details={},
    )
    publish_gate = GateDecision(
        workflow_run_id=workflow.id,
        gate="C",
        outcome="APPROVED",
        artifact_type="draft",
        artifact_id=draft.id,
        artifact_version=draft.version,
        actor_id="fixture-operator",
        reason=None,
        decided_at=now,
        policy_version="1",
        details={"target": "fixture-cms"},
    )
    audit_event = AuditEvent(
        workflow_run_id=workflow.id,
        actor_kind="SYSTEM",
        actor_id="fixture",
        event_type="fixture.workflow.completed",
        entity_type="workflow_run",
        entity_id=workflow.id,
        occurred_at=now,
        payload={"fixture": True},
    )
    session.add_all([topic_gate, editorial_gate, publish_gate, audit_event])
    session.flush()

    publication = Publication(
        workflow_run_id=workflow.id,
        draft_id=draft.id,
        provider="fixture-cms",
        target="fixture-site",
        status="PUBLISHED",
        owner_key=f"publication-{suffix}",
        idempotency_key=f"publication-{suffix}",
        external_id=f"article-{suffix}",
        external_url=f"https://published.example.test/{suffix}",
        scheduled_at=None,
        published_at=now,
        receipt={"ok": True},
    )
    session.add(publication)
    session.flush()

    distribution = DistributionJob(
        workflow_run_id=workflow.id,
        publication_id=publication.id,
        provider="fixture-distributor",
        channel="fixture-social",
        status="POSTED",
        owner_key=f"distribution-{suffix}",
        idempotency_key=f"distribution-{suffix}",
        external_id=f"post-{suffix}",
        external_url=f"https://social.example.test/{suffix}",
        payload={"text": "Fixture distribution"},
        receipt={"ok": True},
    )
    session.add(distribution)
    session.flush()

    performance = PerformanceSnapshot(
        workflow_run_id=workflow.id,
        publication_id=publication.id,
        distribution_job_id=distribution.id,
        captured_at=now,
        metrics={"views": 42, "ctr": 0.12},
    )
    session.add(performance)
    session.commit()

    return CompleteWorkflowFixture(
        source=source,
        source_item=source_item,
        workflow=workflow,
        topic=topic,
        evidence=evidence,
        claim=claim,
        brief=brief,
        draft=draft,
        asset=asset,
        topic_gate=topic_gate,
        editorial_gate=editorial_gate,
        publish_gate=publish_gate,
        audit_event=audit_event,
        publication=publication,
        distribution=distribution,
        performance=performance,
    )
