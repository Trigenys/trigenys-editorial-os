from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select

from editorial_os_api.content_agent import (
    ContentAgent,
    ContentAgentError,
    ContentClaimContext,
    ContentDraftOutput,
    ContentStyleViolationError,
    DraftFactualAssertion,
    DraftSectionOutput,
    InternalLinkSuggestion,
    SeoMetadataOutput,
    VerticalPackMismatchError,
)
from editorial_os_api.domain.enums import (
    ClaimSupportStatus,
    ResearchBriefStatus,
    RiskClass,
    WorkflowStatus,
)
from editorial_os_api.persistence.models import (
    Claim,
    Draft,
    EvidenceItem,
    ResearchBrief,
    TopicCandidate,
    WorkflowRun,
    claim_evidence_links,
    draft_claim_links,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.vertical_packs import (
    VerticalPack,
    generic_demo_pack,
    trigenys_insight_pack,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 29, 13, 0, tzinfo=UTC)


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_verified_run(
    pack: VerticalPack,
    *,
    research_status: ResearchBriefStatus = ResearchBriefStatus.VERIFIED,
    claim_support_status: ClaimSupportStatus = ClaimSupportStatus.SUPPORTED,
    contested: bool = False,
) -> UUID:
    _upgrade_schema()
    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key=pack.key,
            vertical_version=pack.version,
            status=WorkflowStatus.VERIFIED.value,
            risk_class=RiskClass.R0.value,
            confidence_class="C4",
            policy_version="1",
            idempotency_key=f"content-run-{uuid4().hex}",
            context={},
        )
        session.add(run)
        session.flush()

        candidate = TopicCandidate(
            workflow_run_id=run.id,
            version=1,
            cluster_key=f"content-topic-{uuid4().hex}",
            title="Cloud platform launches a new service",
            proposed_angle="Explain what the launch changes for small technical teams.",
            proposed_format="article",
            urgency="NORMAL",
            decision="PROPOSE",
            novelty_score=90,
            relevance_score=90,
            source_diversity_score=75,
            composite_score=88,
            risk_class=RiskClass.R0.value,
            confidence_class="C4",
            reason_codes=["fixture"],
            source_item_ids=[],
            reason_details={},
        )
        session.add(candidate)
        session.flush()

        claim = Claim(
            workflow_run_id=run.id,
            claim_key="service-launch",
            statement="The cloud platform launched the service on 29 September 2026.",
            material=True,
            confidence_class="C4",
            confidence_reason_codes=["PRIMARY_PLUS_INDEPENDENT_CORROBORATION"],
            risk_class=RiskClass.R0.value,
            support_status=claim_support_status.value,
            stale=False,
            contested=contested,
        )
        session.add(claim)
        session.flush()

        evidence = EvidenceItem(
            workflow_run_id=run.id,
            source_item_id=None,
            url="https://official.example.test/launch",
            excerpt="The cloud platform launched the service on 29 September 2026.",
            tier="E4",
            source_role="PRIMARY",
            stale=False,
            extraction_method="fixture",
            metadata_payload={"fixture": True},
            observed_at=NOW,
            published_at=NOW,
            retain_until=None,
            redacted_at=None,
        )
        session.add(evidence)
        session.flush()
        session.execute(
            insert(claim_evidence_links).values(
                claim_id=claim.id,
                evidence_item_id=evidence.id,
                stance="SUPPORTS",
                reason_code="FIXTURE_SUPPORT",
            )
        )

        brief = ResearchBrief(
            workflow_run_id=run.id,
            topic_candidate_id=candidate.id,
            version=1,
            input_fingerprint=f"content-research-{uuid4().hex}",
            status=research_status.value,
            confidence_class="C4",
            risk_class=RiskClass.R0.value,
            reason_codes=["fixture"],
            claim_ids=[str(claim.id)],
            evidence_ids=[str(evidence.id)],
            contradiction_claim_ids=[],
            unsupported_claim_ids=(
                [str(claim.id)]
                if claim_support_status is ClaimSupportStatus.UNSUPPORTED
                else []
            ),
            stale_claim_ids=[],
            source_plan=[],
            budget_usage={},
            review_required=False,
        )
        session.add(brief)
        session.flush()
        return run.id


class FixtureContentAdapter:
    name = "fixture-content"

    def __init__(
        self,
        *,
        include_unknown_claim: bool = False,
        prohibited_phrase: str | None = None,
    ) -> None:
        self.include_unknown_claim = include_unknown_claim
        self.prohibited_phrase = prohibited_phrase
        self.generate_calls = 0
        self.revise_calls = 0
        self.seen_locales: list[str] = []
        self.seen_formats: list[str] = []
        self.seen_claim_keys: list[list[str]] = []

    def generate(
        self,
        workflow_run_id: UUID,
        *,
        claims: list[ContentClaimContext],
        vertical_pack: VerticalPack,
        locale: str,
        content_format: str,
        angle: str,
        call_key: str,
    ) -> ContentDraftOutput:
        del workflow_run_id, angle, call_key
        self.generate_calls += 1
        self._record(claims, locale, content_format)
        return self._output(
            claims,
            vertical_pack=vertical_pack,
            locale=locale,
            revised=False,
        )

    def revise(
        self,
        workflow_run_id: UUID,
        *,
        previous: ContentDraftOutput,
        feedback: str,
        claims: list[ContentClaimContext],
        vertical_pack: VerticalPack,
        locale: str,
        content_format: str,
        angle: str,
        call_key: str,
    ) -> ContentDraftOutput:
        del workflow_run_id, previous, feedback, angle, call_key
        self.revise_calls += 1
        self._record(claims, locale, content_format)
        return self._output(
            claims,
            vertical_pack=vertical_pack,
            locale=locale,
            revised=True,
        )

    def _record(
        self,
        claims: list[ContentClaimContext],
        locale: str,
        content_format: str,
    ) -> None:
        self.seen_locales.append(locale)
        self.seen_formats.append(content_format)
        self.seen_claim_keys.append([claim.claim_key for claim in claims])

    def _output(
        self,
        claims: list[ContentClaimContext],
        *,
        vertical_pack: VerticalPack,
        locale: str,
        revised: bool,
    ) -> ContentDraftOutput:
        known = claims[0]
        assertions = [
            DraftFactualAssertion(
                statement=known.statement,
                claim_key=known.claim_key,
            )
        ]
        if self.include_unknown_claim:
            assertions.append(
                DraftFactualAssertion(
                    statement="The service already has one million paying customers.",
                    claim_key="invented-customer-count",
                )
            )

        phrase = self.prohibited_phrase or ""
        body = (
            f"{phrase} The verified launch matters because teams can now evaluate "
            f"the service from a documented starting point."
        ).strip()
        if locale == "fr":
            body = (
                f"{phrase} Le lancement vérifié donne aux équipes un point de départ "
                f"documenté pour comprendre le service."
            ).strip()

        sections = [
            DraftSectionOutput(
                heading="What changed" if locale == "en" else "Ce qui change",
                body=body,
                factual_assertions=assertions,
            )
        ]
        while len(sections) < vertical_pack.voice.min_sections:
            sections.append(
                DraftSectionOutput(
                    heading="Why it matters" if locale == "en" else "Pourquoi cela compte",
                    body=(
                        "The next question is how teams will use it."
                        if locale == "en"
                        else "La prochaine question est celle de son usage par les équipes."
                    ),
                    factual_assertions=[],
                )
            )

        headline = (
            "Revised cloud service launch"
            if revised
            else "Cloud service launch explained"
        )
        if locale == "fr":
            headline = (
                "Lancement cloud révisé"
                if revised
                else "Comprendre le lancement du service cloud"
            )

        return ContentDraftOutput(
            headline=headline,
            deck=(
                "What the verified launch means for technical teams."
                if locale == "en"
                else "Ce que ce lancement vérifié change pour les équipes techniques."
            ),
            sections=sections,
            seo=SeoMetadataOutput(
                title=(
                    "Cloud service launch"
                    if locale == "en"
                    else "Lancement du service cloud"
                ),
                description=(
                    "A sourced explanation of the new cloud service launch."
                    if locale == "en"
                    else "Une explication sourcée du lancement du nouveau service cloud."
                ),
                keywords=["cloud", "service", "launch"],
                slug=(
                    "cloud-service-launch"
                    if locale == "en"
                    else "lancement-service-cloud"
                ),
            ),
            internal_links=[
                InternalLinkSuggestion(
                    anchor_text="cloud background",
                    target_query="cloud infrastructure explainer",
                    rationale="Adds background without inventing a destination URL.",
                )
            ],
        )


def test_content_agent_generates_from_verified_claim_ledger_with_citations() -> None:
    pack = generic_demo_pack()
    run_id = _create_verified_run(pack)
    adapter = FixtureContentAdapter()

    result = ContentAgent(get_session_factory()).generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
    )

    assert result.workflow_status == WorkflowStatus.DRAFTED.value
    assert result.locale == "en"
    assert result.content_format == "article"
    assert result.vertical_pack_key == "generic-demo"
    assert result.vertical_pack_version == "1"
    assert result.unsupported_factual_claims == []
    assert result.citation_count == 1
    assert adapter.seen_claim_keys == [["service-launch"]]

    with get_session_factory()() as session:
        draft = session.get(Draft, result.draft_id)
        assert draft is not None
        assert draft.research_brief_id is not None
        assert draft.vertical_pack_snapshot["key"] == "generic-demo"
        assert draft.seo_metadata["keywords"] == ["cloud", "service", "launch"]
        assert len(draft.sections) == 1
        assert len(draft.internal_link_suggestions) == 1

        linked = session.scalar(
            select(func.count())
            .select_from(draft_claim_links)
            .where(draft_claim_links.c.draft_id == draft.id)
        )
        assert linked == 1


def test_unknown_factual_assertion_is_persisted_as_unsupported() -> None:
    pack = generic_demo_pack()
    run_id = _create_verified_run(pack)
    adapter = FixtureContentAdapter(include_unknown_claim=True)

    result = ContentAgent(get_session_factory()).generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
    )

    assert result.unsupported_factual_claims == [
        "The service already has one million paying customers."
    ]
    with get_session_factory()() as session:
        draft = session.get(Draft, result.draft_id)
        assert draft is not None
        assert draft.unsupported_factual_claims == result.unsupported_factual_claims


def test_vertical_pack_style_rules_fail_closed_before_persistence() -> None:
    pack = trigenys_insight_pack()
    run_id = _create_verified_run(pack)
    adapter = FixtureContentAdapter(prohibited_phrase="game-changer")
    agent = ContentAgent(get_session_factory())

    with pytest.raises(ContentStyleViolationError):
        agent.generate(
            run_id,
            adapter=adapter,
            vertical_pack=pack,
            locale="en",
        )

    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(Draft)
            .where(Draft.workflow_run_id == run_id)
        )
        assert count == 0
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        assert run.status == WorkflowStatus.VERIFIED.value


def test_trigenys_pack_supports_fr_and_en_without_making_all_packs_bilingual() -> None:
    pack = trigenys_insight_pack()
    run_id = _create_verified_run(pack)
    adapter = FixtureContentAdapter()
    agent = ContentAgent(get_session_factory())

    french = agent.generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
        locale="fr",
    )
    english = agent.generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
        locale="en",
    )

    assert french.locale == "fr"
    assert english.locale == "en"
    assert adapter.seen_locales == ["fr", "en"]

    demo = generic_demo_pack()
    demo_run = _create_verified_run(demo)
    with pytest.raises(ContentAgentError):
        agent.generate(
            demo_run,
            adapter=FixtureContentAdapter(),
            vertical_pack=demo,
            locale="fr",
        )


def test_revision_preserves_research_pack_and_claim_provenance() -> None:
    pack = generic_demo_pack()
    run_id = _create_verified_run(pack)
    adapter = FixtureContentAdapter()
    agent = ContentAgent(get_session_factory())

    original = agent.generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
    )
    revised = agent.revise(
        original.draft_id,
        adapter=adapter,
        feedback="Make the opening more concrete and keep every source reference.",
    )

    assert revised.version == 2
    assert revised.revision_of_id == original.draft_id
    assert revised.workflow_status == WorkflowStatus.DRAFTED.value
    assert adapter.revise_calls == 1

    with get_session_factory()() as session:
        before = session.get(Draft, original.draft_id)
        after = session.get(Draft, revised.draft_id)
        assert before is not None
        assert after is not None
        assert after.research_brief_id == before.research_brief_id
        assert after.editorial_brief_id == before.editorial_brief_id
        assert after.vertical_pack_snapshot == before.vertical_pack_snapshot
        assert after.citations == before.citations
        assert after.revision_feedback is not None

        original_claims = set(
            session.scalars(
                select(draft_claim_links.c.claim_id).where(
                    draft_claim_links.c.draft_id == before.id
                )
            )
        )
        revised_claims = set(
            session.scalars(
                select(draft_claim_links.c.claim_id).where(
                    draft_claim_links.c.draft_id == after.id
                )
            )
        )
        assert revised_claims == original_claims


def test_same_generation_request_is_idempotent_without_second_adapter_call() -> None:
    pack = generic_demo_pack()
    run_id = _create_verified_run(pack)
    adapter = FixtureContentAdapter()
    agent = ContentAgent(get_session_factory())

    first = agent.generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
    )
    second = agent.generate(
        run_id,
        adapter=adapter,
        vertical_pack=pack,
    )

    assert second.draft_id == first.draft_id
    assert adapter.generate_calls == 1


def test_unverified_research_and_pack_version_mismatch_are_rejected() -> None:
    pack = generic_demo_pack()
    run_id = _create_verified_run(
        pack,
        research_status=ResearchBriefStatus.INSUFFICIENT,
    )
    agent = ContentAgent(get_session_factory())

    with pytest.raises(ContentAgentError):
        agent.generate(
            run_id,
            adapter=FixtureContentAdapter(),
            vertical_pack=pack,
        )

    valid_run = _create_verified_run(pack)
    wrong_version = pack.model_copy(update={"version": "2"})
    with pytest.raises(VerticalPackMismatchError):
        agent.generate(
            valid_run,
            adapter=FixtureContentAdapter(),
            vertical_pack=wrong_version,
        )


def test_unsupported_material_claim_in_research_cannot_feed_content_agent() -> None:
    pack = generic_demo_pack()
    run_id = _create_verified_run(
        pack,
        claim_support_status=ClaimSupportStatus.UNSUPPORTED,
    )

    with pytest.raises(ContentAgentError):
        ContentAgent(get_session_factory()).generate(
            run_id,
            adapter=FixtureContentAdapter(),
            vertical_pack=pack,
        )
