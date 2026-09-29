from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.domain.enums import (
    AuditActorKind,
    ClaimSupportStatus,
    ConfidenceClass,
    EvidenceStance,
    EvidenceTier,
    GateKind,
    GateOutcome,
    ResearchBriefStatus,
    RiskClass,
    SourceRole,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.observability import ObservabilityHub, ProductTelemetryEvent
from editorial_os_api.orchestration import PostgresWorkflowEngine, WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    Claim,
    EvidenceItem,
    GateDecision,
    ResearchBrief,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowRun,
    claim_evidence_links,
)
from editorial_os_api.research_verification.contracts import (
    ClaimEvaluation,
    ClaimSeed,
    ResearchAdapter,
    ResearchBudget,
    ResearchSourceDocument,
    ResearchVerificationResult,
    VerificationPolicy,
)
from editorial_os_api.research_verification.policy import (
    LedgerEvidence,
    classify_research_status,
    confidence_at_least,
    evaluate_claim,
    max_risk,
    overall_confidence,
)

_TIER_RANK = {
    EvidenceTier.E0: 0,
    EvidenceTier.E1: 1,
    EvidenceTier.E2: 2,
    EvidenceTier.E3: 3,
    EvidenceTier.E4: 4,
}


class ResearchVerificationError(RuntimeError):
    pass


class ResearchBudgetExceededError(ResearchVerificationError):
    pass


class UnsupportedClaimVerificationError(ResearchVerificationError):
    pass


@dataclass(frozen=True)
class _AcceptedEvidence:
    source: ResearchSourceDocument
    claim_key: str
    stance: EvidenceStance
    excerpt: str
    reason_code: str
    stale: bool


class ResearchVerificationAgent:
    agent_id = "research-verification"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        workflow_engine: PostgresWorkflowEngine | None = None,
        observability: ObservabilityHub | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._workflow_engine = workflow_engine or PostgresWorkflowEngine(session_factory)
        self._observability = observability or ObservabilityHub()

    def verify(
        self,
        workflow_run_id: UUID,
        *,
        adapter: ResearchAdapter,
        budget: ResearchBudget | None = None,
        policy: VerificationPolicy | None = None,
        claim_seeds: list[ClaimSeed] | None = None,
        additional_source_item_ids: list[UUID] | None = None,
        now: datetime | None = None,
    ) -> ResearchVerificationResult:
        selected_budget = budget or ResearchBudget()
        selected_policy = policy or VerificationPolicy()
        observed_now = now or utcnow()

        with self._session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise ResearchVerificationError(
                    f"Unknown workflow run: {workflow_run_id}"
                )
            candidate = self._approved_candidate(session, workflow_run_id)
            sources = self._load_sources(
                session,
                candidate,
                additional_source_item_ids or [],
            )
            fingerprint = self._input_fingerprint(
                candidate=candidate,
                sources=sources,
                adapter_name=adapter.name,
                budget=selected_budget,
                policy=selected_policy,
                claim_seeds=claim_seeds,
            )
            existing = session.scalar(
                select(ResearchBrief).where(
                    ResearchBrief.workflow_run_id == workflow_run_id,
                    ResearchBrief.input_fingerprint == fingerprint,
                )
            )
            if existing is not None:
                self._handoff(existing)
                return self._result(existing)

            if WorkflowStatus(run.status) is not WorkflowStatus.TOPIC_APPROVED:
                raise ResearchVerificationError(
                    "New research requires a Gate-A-approved TOPIC_APPROVED run."
                )
            run_risk = RiskClass(run.risk_class)

        adapter_calls = 0
        reasons: list[str] = []

        if claim_seeds is None:
            if adapter_calls >= selected_budget.max_adapter_calls:
                raise ResearchBudgetExceededError(
                    "Research adapter-call budget exhausted before claim planning."
                )
            planned_claims = adapter.plan_claims(
                workflow_run_id,
                candidate_title=candidate.title,
                candidate_angle=candidate.proposed_angle,
                sources=sources[: selected_budget.max_sources],
                max_claims=selected_budget.max_claims,
                call_key=f"research-plan:{candidate.id}:v{candidate.version}",
            )
            adapter_calls += 1
        else:
            planned_claims = list(claim_seeds)

        self._validate_claim_plan(planned_claims, selected_budget)

        source_limit = min(len(sources), selected_budget.max_sources)
        if len(sources) > source_limit:
            reasons.append("SOURCE_BUDGET_LIMIT_REACHED")

        accepted: list[_AcceptedEvidence] = []
        examined_source_ids: set[UUID] = set()
        evidence_limit_reached = False
        adapter_limit_reached = False

        for source in sources[:source_limit]:
            if adapter_calls >= selected_budget.max_adapter_calls:
                adapter_limit_reached = True
                reasons.append("ADAPTER_CALL_BUDGET_LIMIT_REACHED")
                break

            output = adapter.assess_source(
                workflow_run_id,
                source=source,
                claims=planned_claims,
                call_key=f"research-assess:{candidate.id}:{source.source_item_id}",
            )
            adapter_calls += 1
            examined_source_ids.add(source.source_item_id)

            known_claim_keys = {claim.claim_key for claim in planned_claims}
            seen_assessments: set[tuple[str, str, str]] = set()
            for assessment in output.assessments:
                if assessment.claim_key not in known_claim_keys:
                    reasons.append("UNKNOWN_CLAIM_ASSESSMENT_REJECTED")
                    continue
                if assessment.stance is EvidenceStance.NO_EVIDENCE:
                    continue
                excerpt = (assessment.excerpt or "").strip()
                if not self._excerpt_in_source(excerpt, source.text):
                    reasons.append("EXCERPT_REJECTED_NOT_IN_SOURCE")
                    continue

                signature = (
                    assessment.claim_key,
                    assessment.stance.value,
                    " ".join(excerpt.split()).casefold(),
                )
                if signature in seen_assessments:
                    continue
                seen_assessments.add(signature)

                if len(accepted) >= selected_budget.max_evidence_items:
                    evidence_limit_reached = True
                    reasons.append("EVIDENCE_BUDGET_LIMIT_REACHED")
                    break

                accepted.append(
                    _AcceptedEvidence(
                        source=source,
                        claim_key=assessment.claim_key,
                        stance=assessment.stance,
                        excerpt=excerpt,
                        reason_code=assessment.reason_code,
                        stale=self._is_stale(
                            source,
                            now=observed_now,
                            stale_after_hours=selected_policy.stale_after_hours,
                        ),
                    )
                )

            evaluations = self._evaluate_claims(planned_claims, accepted)
            if self._can_stop_early(
                planned_claims,
                evaluations,
                policy=selected_policy,
            ):
                reasons.append("EARLY_STOP_CONFIDENCE_REACHED")
                break
            if evidence_limit_reached:
                break

        if adapter_limit_reached:
            reasons.append("RESEARCH_STOPPED_BY_ADAPTER_BUDGET")
        if evidence_limit_reached:
            reasons.append("RESEARCH_STOPPED_BY_EVIDENCE_BUDGET")

        evaluations = self._evaluate_claims(planned_claims, accepted)
        material_keys = {
            claim.claim_key for claim in planned_claims if claim.material
        }
        material_evaluations = [
            evaluation
            for evaluation in evaluations
            if evaluation.claim_key in material_keys
        ]
        confidence = overall_confidence(material_evaluations)
        risk = max_risk([run_risk, *[claim.risk_class for claim in planned_claims]])
        status, review_required, status_reasons = classify_research_status(
            evaluations=evaluations,
            material_claim_keys=material_keys,
            risk_class=risk,
            policy=selected_policy,
        )
        reasons.extend(status_reasons)
        reasons = list(dict.fromkeys(reasons))

        with self._session_factory.begin() as session:
            version = (
                session.scalar(
                    select(func.max(ResearchBrief.version)).where(
                        ResearchBrief.workflow_run_id == workflow_run_id
                    )
                )
                or 0
            ) + 1

            evaluation_by_key = {
                evaluation.claim_key: evaluation for evaluation in evaluations
            }
            claim_by_key: dict[str, Claim] = {}
            for seed in planned_claims:
                evaluation = evaluation_by_key[seed.claim_key]
                claim = Claim(
                    workflow_run_id=workflow_run_id,
                    claim_key=seed.claim_key,
                    statement=seed.statement,
                    material=seed.material,
                    confidence_class=evaluation.confidence_class.value,
                    confidence_reason_codes=list(
                        evaluation.confidence_reason_codes
                    ),
                    risk_class=seed.risk_class.value,
                    support_status=evaluation.support_status.value,
                    stale=evaluation.stale,
                    contested=evaluation.contested,
                )
                session.add(claim)
                session.flush()
                claim_by_key[seed.claim_key] = claim

            evidence_ids: list[UUID] = []
            for record in accepted:
                item = EvidenceItem(
                    workflow_run_id=workflow_run_id,
                    source_item_id=record.source.source_item_id,
                    url=record.source.url,
                    excerpt=record.excerpt,
                    tier=record.source.evidence_tier.value,
                    source_role=record.source.source_role.value,
                    stale=record.stale,
                    extraction_method=adapter.name,
                    metadata_payload={
                        "source_id": str(record.source.source_id),
                        "source_name": record.source.source_name,
                        "content_hash": record.source.content_hash,
                        "reason_code": record.reason_code,
                    },
                    observed_at=record.source.observed_at,
                    published_at=record.source.published_at,
                    retain_until=record.source.retain_until,
                    redacted_at=record.source.redacted_at,
                )
                session.add(item)
                session.flush()
                evidence_ids.append(item.id)
                session.execute(
                    insert(claim_evidence_links).values(
                        claim_id=claim_by_key[record.claim_key].id,
                        evidence_item_id=item.id,
                        stance=record.stance.value,
                        reason_code=record.reason_code,
                    )
                )

            contradiction_ids = [
                claim_by_key[evaluation.claim_key].id
                for evaluation in evaluations
                if evaluation.contested
            ]
            unsupported_ids = [
                claim_by_key[evaluation.claim_key].id
                for evaluation in evaluations
                if evaluation.support_status is ClaimSupportStatus.UNSUPPORTED
            ]
            stale_ids = [
                claim_by_key[evaluation.claim_key].id
                for evaluation in evaluations
                if evaluation.stale
            ]

            brief = ResearchBrief(
                workflow_run_id=workflow_run_id,
                topic_candidate_id=candidate.id,
                version=version,
                input_fingerprint=fingerprint,
                status=status.value,
                confidence_class=confidence.value,
                risk_class=risk.value,
                reason_codes=reasons,
                claim_ids=[str(claim.id) for claim in claim_by_key.values()],
                evidence_ids=[str(evidence_id) for evidence_id in evidence_ids],
                contradiction_claim_ids=[
                    str(claim_id) for claim_id in contradiction_ids
                ],
                unsupported_claim_ids=[
                    str(claim_id) for claim_id in unsupported_ids
                ],
                stale_claim_ids=[str(claim_id) for claim_id in stale_ids],
                source_plan=[
                    {
                        "source_item_id": str(source.source_item_id),
                        "source_id": str(source.source_id),
                        "source_name": source.source_name,
                        "role": source.source_role.value,
                        "tier": source.evidence_tier.value,
                        "examined": source.source_item_id in examined_source_ids,
                    }
                    for source in sources
                ],
                budget_usage={
                    "max_sources": selected_budget.max_sources,
                    "sources_examined": len(examined_source_ids),
                    "max_claims": selected_budget.max_claims,
                    "claims_planned": len(planned_claims),
                    "max_evidence_items": selected_budget.max_evidence_items,
                    "evidence_items": len(evidence_ids),
                    "max_adapter_calls": selected_budget.max_adapter_calls,
                    "adapter_calls": adapter_calls,
                },
                review_required=review_required,
            )
            session.add(brief)
            session.flush()
            session.add(
                AuditEvent(
                    workflow_run_id=workflow_run_id,
                    actor_kind=AuditActorKind.AGENT.value,
                    actor_id=self.agent_id,
                    event_type="research.verification.assessed",
                    entity_type="research_brief",
                    entity_id=brief.id,
                    occurred_at=utcnow(),
                    payload={
                        "status": brief.status,
                        "confidence_class": brief.confidence_class,
                        "risk_class": brief.risk_class,
                        "review_required": brief.review_required,
                        "reason_codes": list(brief.reason_codes),
                    },
                )
            )
            brief_id = brief.id

        with self._session_factory() as session:
            persisted = session.get(ResearchBrief, brief_id)
            assert persisted is not None
            self._handoff(persisted)

        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="research verification assessed",
                workflow_run_id=workflow_run_id,
                agent_id=self.agent_id,
                properties={
                    "research_brief_id": str(brief_id),
                    "status": status.value,
                    "confidence_class": confidence.value,
                    "risk_class": risk.value,
                    "review_required": review_required,
                    "claims": len(planned_claims),
                    "evidence_items": len(accepted),
                },
            )
        )

        with self._session_factory() as session:
            final = session.get(ResearchBrief, brief_id)
            assert final is not None
            return self._result(final)

    def resolve_human_review(
        self,
        research_brief_id: UUID,
        *,
        actor_id: str,
        reason: str,
    ) -> ResearchVerificationResult:
        with self._session_factory() as session:
            brief = session.get(ResearchBrief, research_brief_id)
            if brief is None:
                raise ResearchVerificationError(
                    f"Unknown research brief: {research_brief_id}"
                )
            if ResearchBriefStatus(brief.status) is ResearchBriefStatus.REVIEWED:
                return self._result(brief)
            if ResearchBriefStatus(brief.status) is ResearchBriefStatus.INSUFFICIENT:
                raise UnsupportedClaimVerificationError(
                    "Material unsupported claims require new evidence before verification."
                )
            if ResearchBriefStatus(brief.status) is not ResearchBriefStatus.REVIEW_REQUIRED:
                raise ResearchVerificationError(
                    "Human review is only valid for REVIEW_REQUIRED research."
                )
            if RiskClass(brief.risk_class) is RiskClass.R3:
                raise ResearchVerificationError(
                    "R3 research cannot be human-overridden into VERIFIED."
                )
            claims = list(
                session.scalars(
                    select(Claim).where(
                        Claim.id.in_([UUID(value) for value in brief.claim_ids])
                    )
                )
            )
            if any(
                claim.material
                and ClaimSupportStatus(claim.support_status)
                is ClaimSupportStatus.UNSUPPORTED
                for claim in claims
            ):
                raise UnsupportedClaimVerificationError(
                    "Unsupported material claims cannot be marked verified."
                )
            workflow_run_id = brief.workflow_run_id
            version = brief.version

        self._workflow_engine.apply(
            workflow_run_id,
            WorkflowCommand(
                action_key=f"research-review-resume:{research_brief_id}:v{version}",
                action_type=WorkflowActionType.RESUME,
                actor_kind=AuditActorKind.HUMAN,
                actor_id=actor_id,
                payload={
                    "research_brief_id": str(research_brief_id),
                    "reason": reason,
                },
            ),
        )
        self._workflow_engine.apply(
            workflow_run_id,
            WorkflowCommand(
                action_key=f"research-reviewed:{research_brief_id}:v{version}",
                action_type=WorkflowActionType.VERIFICATION_COMPLETED,
                actor_kind=AuditActorKind.HUMAN,
                actor_id=actor_id,
                payload={
                    "research_brief_id": str(research_brief_id),
                    "reviewed": True,
                    "reason": reason,
                },
            ),
        )

        with self._session_factory.begin() as session:
            brief = session.scalar(
                select(ResearchBrief)
                .where(ResearchBrief.id == research_brief_id)
                .with_for_update()
            )
            assert brief is not None
            brief.status = ResearchBriefStatus.REVIEWED.value
            brief.review_required = False
            brief.review_resolved_by = actor_id
            brief.review_resolved_at = utcnow()
            session.add(
                AuditEvent(
                    workflow_run_id=workflow_run_id,
                    actor_kind=AuditActorKind.HUMAN.value,
                    actor_id=actor_id,
                    event_type="research.verification.review_resolved",
                    entity_type="research_brief",
                    entity_id=brief.id,
                    occurred_at=utcnow(),
                    payload={
                        "reason": reason,
                        "research_brief_version": version,
                    },
                )
            )

        with self._session_factory() as session:
            brief = session.get(ResearchBrief, research_brief_id)
            assert brief is not None
            return self._result(brief)

    def _handoff(self, brief: ResearchBrief) -> None:
        status = ResearchBriefStatus(brief.status)
        if status in {ResearchBriefStatus.VERIFIED, ResearchBriefStatus.REVIEWED}:
            self._workflow_engine.apply(
                brief.workflow_run_id,
                WorkflowCommand(
                    action_key=f"research-verified:{brief.id}:v{brief.version}",
                    action_type=WorkflowActionType.VERIFICATION_COMPLETED,
                    actor_kind=AuditActorKind.AGENT,
                    actor_id=self.agent_id,
                    payload={
                        "research_brief_id": str(brief.id),
                        "research_brief_version": brief.version,
                        "confidence_class": brief.confidence_class,
                        "risk_class": brief.risk_class,
                    },
                ),
            )
            return

        self._workflow_engine.apply(
            brief.workflow_run_id,
            WorkflowCommand(
                action_key=f"research-block:{brief.id}:v{brief.version}",
                action_type=WorkflowActionType.BLOCK,
                actor_kind=AuditActorKind.AGENT,
                actor_id=self.agent_id,
                payload={
                    "research_brief_id": str(brief.id),
                    "research_brief_version": brief.version,
                    "status": brief.status,
                    "reason_codes": list(brief.reason_codes),
                },
            ),
        )

    def _approved_candidate(
        self,
        session: Session,
        workflow_run_id: UUID,
    ) -> TopicCandidate:
        decision = session.scalar(
            select(GateDecision)
            .where(
                GateDecision.workflow_run_id == workflow_run_id,
                GateDecision.gate == GateKind.TOPIC.value,
                GateDecision.outcome == GateOutcome.APPROVED.value,
                GateDecision.artifact_type == "topic_candidate",
            )
            .order_by(GateDecision.decided_at.desc())
        )
        if decision is None:
            raise ResearchVerificationError(
                "Research requires an approved Gate A topic candidate."
            )
        candidate = session.get(TopicCandidate, decision.artifact_id)
        if candidate is None:
            raise ResearchVerificationError(
                "Approved Gate A topic candidate no longer exists."
            )
        if candidate.version != decision.artifact_version:
            raise ResearchVerificationError(
                "Approved Gate A version does not match the current topic candidate."
            )
        return candidate

    def _load_sources(
        self,
        session: Session,
        candidate: TopicCandidate,
        additional_source_item_ids: list[UUID],
    ) -> list[ResearchSourceDocument]:
        ids = {
            *[UUID(value) for value in candidate.source_item_ids],
            *additional_source_item_ids,
        }
        if not ids:
            raise ResearchVerificationError(
                "Research requires at least one source item."
            )

        rows = list(
            session.execute(
                select(SourceItem, Source)
                .join(Source, Source.id == SourceItem.source_id)
                .where(SourceItem.id.in_(ids))
            )
        )
        if len(rows) != len(ids):
            raise ResearchVerificationError(
                "One or more research source items do not exist."
            )

        documents: list[ResearchSourceDocument] = []
        for item, source in rows:
            tier = self._best_tier(
                EvidenceTier(source.trust_tier),
                EvidenceTier(source.default_evidence_tier),
            )
            role = (
                SourceRole.PRIMARY
                if _TIER_RANK[tier] >= _TIER_RANK[EvidenceTier.E3]
                else SourceRole.SECONDARY
            )
            body_value = item.extracted_payload.get("body", "")
            summary_value = item.extracted_payload.get("summary", "")
            body = body_value if isinstance(body_value, str) else ""
            summary = summary_value if isinstance(summary_value, str) else ""
            text = "\n".join(
                part for part in [item.title or "", body, summary] if part.strip()
            )
            documents.append(
                ResearchSourceDocument(
                    source_item_id=item.id,
                    source_id=source.id,
                    source_name=source.name,
                    url=item.canonical_url,
                    title=item.title or item.canonical_url,
                    text=text,
                    evidence_tier=tier,
                    source_role=role,
                    content_hash=item.content_hash,
                    published_at=item.published_at,
                    observed_at=item.observed_at,
                    retain_until=item.retain_until,
                    redacted_at=item.redacted_at,
                )
            )

        return sorted(
            documents,
            key=lambda source: (
                0 if source.source_role is SourceRole.PRIMARY else 1,
                -_TIER_RANK[source.evidence_tier],
                -(source.published_at or source.observed_at).timestamp(),
                str(source.source_item_id),
            ),
        )

    @staticmethod
    def _validate_claim_plan(
        claims: list[ClaimSeed],
        budget: ResearchBudget,
    ) -> None:
        if not claims:
            raise ResearchVerificationError(
                "Research adapter produced no claims to verify."
            )
        if len(claims) > budget.max_claims:
            raise ResearchBudgetExceededError(
                "Claim plan exceeds configured research claim budget."
            )
        keys = [claim.claim_key for claim in claims]
        if len(keys) != len(set(keys)):
            raise ResearchVerificationError(
                "Research claim keys must be unique."
            )

    @staticmethod
    def _input_fingerprint(
        *,
        candidate: TopicCandidate,
        sources: list[ResearchSourceDocument],
        adapter_name: str,
        budget: ResearchBudget,
        policy: VerificationPolicy,
        claim_seeds: list[ClaimSeed] | None,
    ) -> str:
        payload = {
            "candidate_id": str(candidate.id),
            "candidate_version": candidate.version,
            "source_item_ids": sorted(str(source.source_item_id) for source in sources),
            "adapter": adapter_name,
            "budget": budget.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            "claims": (
                [claim.model_dump(mode="json") for claim in claim_seeds]
                if claim_seeds is not None
                else "adapter-planned"
            ),
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _evaluate_claims(
        claims: list[ClaimSeed],
        accepted: list[_AcceptedEvidence],
    ) -> list[ClaimEvaluation]:
        return [
            evaluate_claim(
                claim,
                [
                    LedgerEvidence(
                        source_id=record.source.source_id,
                        tier=record.source.evidence_tier,
                        stance=record.stance,
                        stale=record.stale,
                    )
                    for record in accepted
                    if record.claim_key == claim.claim_key
                ],
            )
            for claim in claims
        ]

    @staticmethod
    def _can_stop_early(
        claims: list[ClaimSeed],
        evaluations: list[ClaimEvaluation],
        *,
        policy: VerificationPolicy,
    ) -> bool:
        material_keys = {claim.claim_key for claim in claims if claim.material}
        material = [
            evaluation
            for evaluation in evaluations
            if evaluation.claim_key in material_keys
        ]
        return bool(material) and all(
            confidence_at_least(
                evaluation.confidence_class,
                policy.early_stop_confidence,
            )
            and evaluation.supporting_source_count
            >= policy.early_stop_independent_sources
            and not evaluation.contested
            and not evaluation.stale
            and evaluation.support_status is ClaimSupportStatus.SUPPORTED
            for evaluation in material
        )

    @staticmethod
    def _excerpt_in_source(excerpt: str, source_text: str) -> bool:
        if not excerpt:
            return False
        normalized_excerpt = " ".join(excerpt.split()).casefold()
        normalized_source = " ".join(source_text.split()).casefold()
        return normalized_excerpt in normalized_source

    @staticmethod
    def _is_stale(
        source: ResearchSourceDocument,
        *,
        now: datetime,
        stale_after_hours: int,
    ) -> bool:
        timestamp = source.published_at or source.observed_at
        return now - timestamp > timedelta(hours=stale_after_hours)

    @staticmethod
    def _best_tier(left: EvidenceTier, right: EvidenceTier) -> EvidenceTier:
        return left if _TIER_RANK[left] >= _TIER_RANK[right] else right

    def _result(self, brief: ResearchBrief) -> ResearchVerificationResult:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, brief.workflow_run_id)
            if run is None:
                raise ResearchVerificationError(
                    f"Unknown workflow run: {brief.workflow_run_id}"
                )
            workflow_status = run.status

        return ResearchVerificationResult(
            workflow_run_id=brief.workflow_run_id,
            research_brief_id=brief.id,
            research_brief_version=brief.version,
            status=ResearchBriefStatus(brief.status),
            confidence_class=ConfidenceClass(brief.confidence_class),
            risk_class=RiskClass(brief.risk_class),
            review_required=brief.review_required,
            claim_ids=[UUID(value) for value in brief.claim_ids],
            evidence_ids=[UUID(value) for value in brief.evidence_ids],
            contradiction_claim_ids=[
                UUID(value) for value in brief.contradiction_claim_ids
            ],
            unsupported_claim_ids=[
                UUID(value) for value in brief.unsupported_claim_ids
            ],
            stale_claim_ids=[UUID(value) for value in brief.stale_claim_ids],
            reason_codes=list(brief.reason_codes),
            workflow_status=workflow_status,
        )
