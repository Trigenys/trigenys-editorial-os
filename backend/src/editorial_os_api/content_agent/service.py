from __future__ import annotations

import json
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.content_agent.contracts import (
    ContentAdapter,
    ContentAgentResult,
    ContentClaimContext,
    ContentDraftOutput,
    ContentEvidenceReference,
)
from editorial_os_api.domain.enums import (
    AuditActorKind,
    ClaimSupportStatus,
    ConfidenceClass,
    ResearchBriefStatus,
    RiskClass,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.observability import ObservabilityHub, ProductTelemetryEvent
from editorial_os_api.orchestration import PostgresWorkflowEngine, WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    AuditEvent,
    Claim,
    Draft,
    EditorialBrief,
    EvidenceItem,
    ResearchBrief,
    TopicCandidate,
    WorkflowRun,
    brief_claim_links,
    claim_evidence_links,
    draft_claim_links,
)
from editorial_os_api.vertical_packs import VerticalPack


class ContentAgentError(RuntimeError):
    pass


class VerticalPackMismatchError(ContentAgentError):
    pass


class ContentStyleViolationError(ContentAgentError):
    pass


class ContentAgent:
    agent_id = "content"

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

    def generate(
        self,
        workflow_run_id: UUID,
        *,
        adapter: ContentAdapter,
        vertical_pack: VerticalPack,
        locale: str | None = None,
        content_format: str | None = None,
    ) -> ContentAgentResult:
        selected_locale = locale or vertical_pack.default_locale
        selected_format = content_format or vertical_pack.default_format
        self._validate_pack_request(
            vertical_pack,
            locale=selected_locale,
            content_format=selected_format,
        )

        with self._session_factory() as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None:
                raise ContentAgentError(f"Unknown workflow run: {workflow_run_id}")
            self._assert_pack_matches_run(run, vertical_pack)
            if WorkflowStatus(run.status) not in {
                WorkflowStatus.VERIFIED,
                WorkflowStatus.DRAFTED,
            }:
                raise ContentAgentError(
                    "Content generation requires a VERIFIED or DRAFTED workflow."
                )

            research = self._latest_usable_research(session, workflow_run_id)
            candidate = session.get(TopicCandidate, research.topic_candidate_id)
            if candidate is None:
                raise ContentAgentError("Research topic candidate no longer exists.")
            claims = self._claim_contexts(
                session,
                research,
                vertical_pack=vertical_pack,
            )
            fingerprint = self._input_fingerprint(
                research=research,
                vertical_pack=vertical_pack,
                locale=selected_locale,
                content_format=selected_format,
                adapter_name=adapter.name,
                revision_of_id=None,
                revision_feedback=None,
            )
            existing = session.scalar(
                select(Draft).where(
                    Draft.workflow_run_id == workflow_run_id,
                    Draft.locale == selected_locale,
                    Draft.input_fingerprint == fingerprint,
                )
            )
            if existing is not None:
                self._handoff_initial(existing)
                return self._result(existing)
            angle = candidate.proposed_angle

        output = adapter.generate(
            workflow_run_id,
            claims=claims,
            vertical_pack=vertical_pack,
            locale=selected_locale,
            content_format=selected_format,
            angle=angle,
            call_key=(
                f"content-generate:{research.id}:v{research.version}:"
                f"{vertical_pack.key}:{vertical_pack.version}:"
                f"{selected_locale}:{selected_format}"
            ),
        )
        self._validate_output(output, vertical_pack)
        used_claims, unsupported, citations = self._resolve_assertions(
            output,
            claims,
            vertical_pack=vertical_pack,
        )

        with self._session_factory.begin() as session:
            version = (
                session.scalar(
                    select(func.max(Draft.version)).where(
                        Draft.workflow_run_id == workflow_run_id,
                        Draft.locale == selected_locale,
                    )
                )
                or 0
            ) + 1
            brief_version = (
                session.scalar(
                    select(func.max(EditorialBrief.version)).where(
                        EditorialBrief.workflow_run_id == workflow_run_id
                    )
                )
                or 0
            ) + 1

            brief = EditorialBrief(
                workflow_run_id=workflow_run_id,
                version=brief_version,
                angle=angle,
                locale=selected_locale,
                instructions={
                    "research_brief_id": str(research.id),
                    "research_brief_version": research.version,
                    "content_format": selected_format,
                    "vertical_pack": vertical_pack.model_dump(mode="json"),
                },
            )
            session.add(brief)
            session.flush()

            authorized_claim_ids = [context.claim_id for context in claims]
            for claim_id in authorized_claim_ids:
                session.execute(
                    insert(brief_claim_links).values(
                        editorial_brief_id=brief.id,
                        claim_id=claim_id,
                    )
                )

            draft = Draft(
                workflow_run_id=workflow_run_id,
                editorial_brief_id=brief.id,
                research_brief_id=research.id,
                revision_of_id=None,
                version=version,
                locale=selected_locale,
                content_format=selected_format,
                vertical_pack_key=vertical_pack.key,
                vertical_pack_version=vertical_pack.version,
                input_fingerprint=fingerprint,
                title=output.headline,
                deck=output.deck,
                body=self._render_body(output),
                sections=[
                    section.model_dump(mode="json") for section in output.sections
                ],
                seo_metadata=output.seo.model_dump(mode="json"),
                citations=citations,
                internal_link_suggestions=[
                    suggestion.model_dump(mode="json")
                    for suggestion in output.internal_links
                ],
                unsupported_factual_claims=unsupported,
                vertical_pack_snapshot=vertical_pack.model_dump(mode="json"),
                revision_feedback=None,
                metadata_payload={
                    "adapter": adapter.name,
                    "research_brief_version": research.version,
                    "authorized_claim_count": len(authorized_claim_ids),
                    "used_claim_count": len(used_claims),
                },
            )
            session.add(draft)
            session.flush()

            self._persist_draft_claim_links(
                session,
                draft_id=draft.id,
                used_claims=used_claims,
            )
            self._record_audit(
                session,
                draft=draft,
                event_type="content.draft.created",
                payload={
                    "vertical_pack_key": vertical_pack.key,
                    "vertical_pack_version": vertical_pack.version,
                    "locale": selected_locale,
                    "content_format": selected_format,
                    "unsupported_factual_claim_count": len(unsupported),
                },
            )
            draft_id = draft.id

        with self._session_factory() as session:
            persisted = session.get(Draft, draft_id)
            assert persisted is not None
            self._handoff_initial(persisted)

        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="content draft created",
                workflow_run_id=workflow_run_id,
                agent_id=self.agent_id,
                properties={
                    "draft_id": str(draft_id),
                    "locale": selected_locale,
                    "content_format": selected_format,
                    "vertical_pack_key": vertical_pack.key,
                    "vertical_pack_version": vertical_pack.version,
                    "unsupported_factual_claim_count": len(unsupported),
                },
            )
        )

        with self._session_factory() as session:
            persisted = session.get(Draft, draft_id)
            assert persisted is not None
            return self._result(persisted)

    def revise(
        self,
        draft_id: UUID,
        *,
        adapter: ContentAdapter,
        feedback: str,
    ) -> ContentAgentResult:
        normalized_feedback = feedback.strip()
        if not normalized_feedback:
            raise ValueError("feedback cannot be empty.")

        with self._session_factory() as session:
            previous = session.get(Draft, draft_id)
            if previous is None:
                raise ContentAgentError(f"Unknown draft: {draft_id}")
            run = session.get(WorkflowRun, previous.workflow_run_id)
            if run is None:
                raise ContentAgentError("Draft workflow run no longer exists.")
            if WorkflowStatus(run.status) is not WorkflowStatus.DRAFTED:
                raise ContentAgentError(
                    "Draft revision requires workflow status DRAFTED."
                )
            if previous.research_brief_id is None:
                raise ContentAgentError(
                    "Legacy draft has no research brief provenance for safe revision."
                )
            research = session.get(ResearchBrief, previous.research_brief_id)
            if research is None:
                raise ContentAgentError("Draft research brief no longer exists.")
            pack = VerticalPack.model_validate(previous.vertical_pack_snapshot)
            self._assert_pack_matches_run(run, pack)
            claims = self._claim_contexts(
                session,
                research,
                vertical_pack=pack,
            )
            brief = session.get(EditorialBrief, previous.editorial_brief_id)
            if brief is None:
                raise ContentAgentError("Draft editorial brief no longer exists.")

            fingerprint = self._input_fingerprint(
                research=research,
                vertical_pack=pack,
                locale=previous.locale,
                content_format=previous.content_format,
                adapter_name=adapter.name,
                revision_of_id=previous.id,
                revision_feedback=normalized_feedback,
            )
            existing = session.scalar(
                select(Draft).where(
                    Draft.workflow_run_id == previous.workflow_run_id,
                    Draft.locale == previous.locale,
                    Draft.input_fingerprint == fingerprint,
                )
            )
            if existing is not None:
                return self._result(existing)

            previous_output = self._draft_output(previous)
            angle = brief.angle
            workflow_run_id = previous.workflow_run_id
            locale = previous.locale
            content_format = previous.content_format

        output = adapter.revise(
            workflow_run_id,
            previous=previous_output,
            feedback=normalized_feedback,
            claims=claims,
            vertical_pack=pack,
            locale=locale,
            content_format=content_format,
            angle=angle,
            call_key=f"content-revise:{draft_id}:{fingerprint[:20]}",
        )
        self._validate_output(output, pack)
        used_claims, unsupported, citations = self._resolve_assertions(
            output,
            claims,
            vertical_pack=pack,
        )

        with self._session_factory.begin() as session:
            previous = session.get(Draft, draft_id)
            assert previous is not None
            version = (
                session.scalar(
                    select(func.max(Draft.version)).where(
                        Draft.workflow_run_id == workflow_run_id,
                        Draft.locale == locale,
                    )
                )
                or 0
            ) + 1

            draft = Draft(
                workflow_run_id=workflow_run_id,
                editorial_brief_id=previous.editorial_brief_id,
                research_brief_id=previous.research_brief_id,
                revision_of_id=previous.id,
                version=version,
                locale=locale,
                content_format=content_format,
                vertical_pack_key=previous.vertical_pack_key,
                vertical_pack_version=previous.vertical_pack_version,
                input_fingerprint=fingerprint,
                title=output.headline,
                deck=output.deck,
                body=self._render_body(output),
                sections=[
                    section.model_dump(mode="json") for section in output.sections
                ],
                seo_metadata=output.seo.model_dump(mode="json"),
                citations=citations,
                internal_link_suggestions=[
                    suggestion.model_dump(mode="json")
                    for suggestion in output.internal_links
                ],
                unsupported_factual_claims=unsupported,
                vertical_pack_snapshot=dict(previous.vertical_pack_snapshot),
                revision_feedback=normalized_feedback,
                metadata_payload={
                    **previous.metadata_payload,
                    "adapter": adapter.name,
                    "revised_from": str(previous.id),
                },
            )
            session.add(draft)
            session.flush()
            self._persist_draft_claim_links(
                session,
                draft_id=draft.id,
                used_claims=used_claims,
            )
            self._record_audit(
                session,
                draft=draft,
                event_type="content.draft.revised",
                payload={
                    "revision_of_id": str(previous.id),
                    "feedback": normalized_feedback,
                    "unsupported_factual_claim_count": len(unsupported),
                },
            )
            revised_id = draft.id

        with self._session_factory() as session:
            persisted = session.get(Draft, revised_id)
            assert persisted is not None
            return self._result(persisted)

    def _claim_contexts(
        self,
        session: Session,
        research: ResearchBrief,
        *,
        vertical_pack: VerticalPack,
    ) -> list[ContentClaimContext]:
        claim_ids = [UUID(value) for value in research.claim_ids]
        claims = list(
            session.scalars(
                select(Claim).where(Claim.id.in_(claim_ids))
            )
        )
        claim_by_id = {claim.id: claim for claim in claims}
        if set(claim_by_id) != set(claim_ids):
            raise ContentAgentError("Research brief references missing claims.")

        link_rows = list(
            session.execute(
                select(
                    claim_evidence_links.c.claim_id,
                    claim_evidence_links.c.evidence_item_id,
                    claim_evidence_links.c.stance,
                ).where(claim_evidence_links.c.claim_id.in_(claim_ids))
            )
        )
        evidence_ids = {
            row.evidence_item_id
            for row in link_rows
        }
        evidence_by_id = {
            item.id: item
            for item in session.scalars(
                select(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids))
            )
        }
        links_by_claim: dict[UUID, list[ContentEvidenceReference]] = {}
        for row in link_rows:
            evidence = evidence_by_id.get(row.evidence_item_id)
            if evidence is None:
                continue
            links_by_claim.setdefault(row.claim_id, []).append(
                ContentEvidenceReference(
                    evidence_id=evidence.id,
                    url=evidence.url,
                    tier=evidence.tier,
                    stance=row.stance,
                )
            )

        contexts: list[ContentClaimContext] = []
        for claim_id in claim_ids:
            claim = claim_by_id[claim_id]
            support_status = ClaimSupportStatus(claim.support_status)
            if claim.material and support_status is ClaimSupportStatus.UNSUPPORTED:
                raise ContentAgentError(
                    "Verified research contains an unsupported material claim."
                )
            if (
                claim.contested
                and not vertical_pack.source_rules.allow_reviewed_contested_claims
            ):
                raise ContentAgentError(
                    "Vertical pack forbids reviewed contested claims."
                )
            references = sorted(
                links_by_claim.get(claim.id, []),
                key=lambda reference: (
                    reference.url,
                    str(reference.evidence_id),
                    reference.stance,
                ),
            )
            if (
                claim.material
                and vertical_pack.source_rules.require_citations_for_material_claims
                and not references
            ):
                raise ContentAgentError(
                    "Material claim has no evidence references for content generation."
                )
            contexts.append(
                ContentClaimContext(
                    claim_id=claim.id,
                    claim_key=claim.claim_key,
                    statement=claim.statement,
                    material=claim.material,
                    confidence_class=ConfidenceClass(claim.confidence_class),
                    risk_class=RiskClass(claim.risk_class),
                    support_status=support_status,
                    contested=claim.contested,
                    stale=claim.stale,
                    evidence=references,
                )
            )
        return contexts

    @staticmethod
    def _latest_usable_research(
        session: Session,
        workflow_run_id: UUID,
    ) -> ResearchBrief:
        research = session.scalar(
            select(ResearchBrief)
            .where(
                ResearchBrief.workflow_run_id == workflow_run_id,
                ResearchBrief.status.in_(
                    [
                        ResearchBriefStatus.VERIFIED.value,
                        ResearchBriefStatus.REVIEWED.value,
                    ]
                ),
            )
            .order_by(ResearchBrief.version.desc())
        )
        if research is None:
            raise ContentAgentError(
                "Content generation requires VERIFIED or REVIEWED research."
            )
        return research

    @staticmethod
    def _validate_pack_request(
        vertical_pack: VerticalPack,
        *,
        locale: str,
        content_format: str,
    ) -> None:
        if not vertical_pack.supports(
            locale=locale,
            content_format=content_format,
        ):
            raise ContentAgentError(
                f"Vertical pack {vertical_pack.key!r} version "
                f"{vertical_pack.version!r} does not support "
                f"locale={locale!r}, format={content_format!r}."
            )

    @staticmethod
    def _assert_pack_matches_run(
        run: WorkflowRun,
        vertical_pack: VerticalPack,
    ) -> None:
        if run.vertical_key != vertical_pack.key:
            raise VerticalPackMismatchError(
                "Vertical pack key does not match workflow vertical."
            )
        if run.vertical_version != vertical_pack.version:
            raise VerticalPackMismatchError(
                "Vertical pack version does not match workflow vertical version."
            )

    @staticmethod
    def _validate_output(
        output: ContentDraftOutput,
        vertical_pack: VerticalPack,
    ) -> None:
        voice = vertical_pack.voice
        if len(output.headline) > voice.max_headline_chars:
            raise ContentStyleViolationError(
                "Headline exceeds vertical-pack maximum."
            )
        if output.deck is not None and len(output.deck) > voice.max_deck_chars:
            raise ContentStyleViolationError(
                "Deck exceeds vertical-pack maximum."
            )
        if len(output.sections) < voice.min_sections:
            raise ContentStyleViolationError(
                "Draft has fewer sections than the vertical pack requires."
            )
        if len(output.seo.title) > vertical_pack.seo.title_max_chars:
            raise ContentStyleViolationError(
                "SEO title exceeds vertical-pack maximum."
            )
        if len(output.seo.description) > vertical_pack.seo.description_max_chars:
            raise ContentStyleViolationError(
                "SEO description exceeds vertical-pack maximum."
            )
        if vertical_pack.seo.require_keywords and not output.seo.keywords:
            raise ContentStyleViolationError(
                "Vertical pack requires SEO keywords."
            )

        searchable = "\n".join(
            [
                output.headline,
                output.deck or "",
                *(section.body for section in output.sections),
                output.seo.title,
                output.seo.description,
            ]
        ).casefold()
        for phrase in voice.prohibited_phrases:
            if phrase.casefold() in searchable:
                raise ContentStyleViolationError(
                    f"Draft contains prohibited phrase: {phrase!r}."
                )

    @staticmethod
    def _resolve_assertions(
        output: ContentDraftOutput,
        claims: list[ContentClaimContext],
        *,
        vertical_pack: VerticalPack,
    ) -> tuple[dict[UUID, ClaimSupportStatus], list[str], list[dict[str, object]]]:
        claim_by_key = {claim.claim_key: claim for claim in claims}
        used_claims: dict[UUID, ClaimSupportStatus] = {}
        unsupported: list[str] = []
        citation_keys: set[tuple[UUID, UUID, str]] = set()
        citations: list[dict[str, object]] = []

        for section in output.sections:
            for assertion in section.factual_assertions:
                claim = (
                    claim_by_key.get(assertion.claim_key)
                    if assertion.claim_key is not None
                    else None
                )
                if claim is None:
                    unsupported.append(assertion.statement)
                    continue

                used_claims[claim.claim_id] = claim.support_status
                if (
                    claim.material
                    and vertical_pack.source_rules.require_citations_for_material_claims
                    and not claim.evidence
                ):
                    unsupported.append(assertion.statement)
                    continue

                for reference in claim.evidence:
                    key = (claim.claim_id, reference.evidence_id, reference.stance)
                    if key in citation_keys:
                        continue
                    citation_keys.add(key)
                    citations.append(
                        {
                            "claim_id": str(claim.claim_id),
                            "claim_key": claim.claim_key,
                            "evidence_id": str(reference.evidence_id),
                            "url": reference.url,
                            "tier": reference.tier,
                            "stance": reference.stance,
                        }
                    )

        return (
            used_claims,
            list(dict.fromkeys(unsupported)),
            citations,
        )

    @staticmethod
    def _persist_draft_claim_links(
        session: Session,
        *,
        draft_id: UUID,
        used_claims: dict[UUID, ClaimSupportStatus],
    ) -> None:
        for claim_id, support_status in used_claims.items():
            session.execute(
                insert(draft_claim_links).values(
                    draft_id=draft_id,
                    claim_id=claim_id,
                    support_status=support_status.value,
                )
            )

    @staticmethod
    def _render_body(output: ContentDraftOutput) -> str:
        rendered: list[str] = []
        for section in output.sections:
            if section.heading:
                rendered.append(f"## {section.heading}\n\n{section.body}")
            else:
                rendered.append(section.body)
        return "\n\n".join(rendered)

    @staticmethod
    def _draft_output(draft: Draft) -> ContentDraftOutput:
        return ContentDraftOutput.model_validate(
            {
                "headline": draft.title,
                "deck": draft.deck,
                "sections": draft.sections,
                "seo": draft.seo_metadata,
                "internal_links": draft.internal_link_suggestions,
            }
        )

    @staticmethod
    def _input_fingerprint(
        *,
        research: ResearchBrief,
        vertical_pack: VerticalPack,
        locale: str,
        content_format: str,
        adapter_name: str,
        revision_of_id: UUID | None,
        revision_feedback: str | None,
    ) -> str:
        payload = {
            "research_brief_id": str(research.id),
            "research_brief_version": research.version,
            "vertical_pack": vertical_pack.model_dump(mode="json"),
            "locale": locale,
            "content_format": content_format,
            "adapter": adapter_name,
            "revision_of_id": str(revision_of_id) if revision_of_id else None,
            "revision_feedback": revision_feedback,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _handoff_initial(self, draft: Draft) -> None:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, draft.workflow_run_id)
            if run is None:
                raise ContentAgentError("Draft workflow run no longer exists.")
            status = WorkflowStatus(run.status)

        if status is WorkflowStatus.DRAFTED:
            return
        if status is not WorkflowStatus.VERIFIED:
            raise ContentAgentError(
                f"Draft handoff is not legal from workflow status {status.value}."
            )

        self._workflow_engine.apply(
            draft.workflow_run_id,
            WorkflowCommand(
                action_key=f"content-drafted:{draft.id}:v{draft.version}",
                action_type=WorkflowActionType.DRAFT_COMPLETED,
                actor_kind=AuditActorKind.AGENT,
                actor_id=self.agent_id,
                payload={
                    "draft_id": str(draft.id),
                    "draft_version": draft.version,
                    "locale": draft.locale,
                    "content_format": draft.content_format,
                    "vertical_pack_key": draft.vertical_pack_key,
                    "vertical_pack_version": draft.vertical_pack_version,
                    "unsupported_factual_claim_count": len(
                        draft.unsupported_factual_claims
                    ),
                },
            ),
        )

    @staticmethod
    def _record_audit(
        session: Session,
        *,
        draft: Draft,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        session.add(
            AuditEvent(
                workflow_run_id=draft.workflow_run_id,
                actor_kind=AuditActorKind.AGENT.value,
                actor_id="content",
                event_type=event_type,
                entity_type="draft",
                entity_id=draft.id,
                occurred_at=utcnow(),
                payload=payload,
            )
        )

    def _result(self, draft: Draft) -> ContentAgentResult:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, draft.workflow_run_id)
            if run is None:
                raise ContentAgentError("Draft workflow run no longer exists.")
            used_claim_ids = [
                UUID(str(value))
                for value in session.scalars(
                    select(draft_claim_links.c.claim_id).where(
                        draft_claim_links.c.draft_id == draft.id
                    )
                )
            ]

        return ContentAgentResult(
            workflow_run_id=draft.workflow_run_id,
            draft_id=draft.id,
            version=draft.version,
            locale=draft.locale,
            content_format=draft.content_format,
            vertical_pack_key=draft.vertical_pack_key,
            vertical_pack_version=draft.vertical_pack_version,
            claim_ids=used_claim_ids,
            unsupported_factual_claims=list(draft.unsupported_factual_claims),
            citation_count=len(draft.citations),
            revision_of_id=draft.revision_of_id,
            workflow_status=run.status,
        )
