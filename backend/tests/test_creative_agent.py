from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from editorial_os_api.creative_agent import (
    AssetPolicyError,
    AssetVariantSpec,
    CreativeAgent,
    ProviderAsset,
    VisualAssetSpec,
    VisualBrief,
    VisualBriefValidationError,
)
from editorial_os_api.domain.enums import (
    AssetKind,
    AssetManifestStatus,
    AssetOrigin,
    AssetRightsStatus,
    WorkflowStatus,
)
from editorial_os_api.persistence.models import (
    Asset,
    AssetManifest,
    Draft,
    EditorialBrief,
    WorkflowRun,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.vertical_packs import (
    VerticalPack,
    generic_demo_pack,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def _create_drafted_run(
    pack: VerticalPack,
    *,
    locale: str | None = None,
) -> UUID:
    _upgrade_schema()
    selected_locale = locale or pack.default_locale
    with get_session_factory().begin() as session:
        run = WorkflowRun(
            vertical_key=pack.key,
            vertical_version=pack.version,
            status=WorkflowStatus.DRAFTED.value,
            risk_class="R0",
            confidence_class="C4",
            policy_version="1",
            idempotency_key=f"creative-run-{uuid4().hex}",
            context={},
        )
        session.add(run)
        session.flush()

        brief = EditorialBrief(
            workflow_run_id=run.id,
            version=1,
            angle="Explain the launch without overstating the visuals.",
            locale=selected_locale,
            instructions={"fixture": True},
        )
        session.add(brief)
        session.flush()

        draft = Draft(
            workflow_run_id=run.id,
            editorial_brief_id=brief.id,
            research_brief_id=None,
            revision_of_id=None,
            version=1,
            locale=selected_locale,
            content_format=pack.default_format,
            vertical_pack_key=pack.key,
            vertical_pack_version=pack.version,
            input_fingerprint=f"creative-draft-{uuid4().hex}",
            title="A verified service launch",
            deck="What the launch means for technical teams.",
            body="The service launch is documented in the verified claim ledger.",
            sections=[],
            seo_metadata={},
            citations=[],
            internal_link_suggestions=[],
            unsupported_factual_claims=[],
            vertical_pack_snapshot=pack.model_dump(mode="json"),
            revision_feedback=None,
            metadata_payload={"fixture": True},
        )
        session.add(draft)
        session.flush()
        return draft.id


class FixturePlanner:
    name = "fixture-planner"

    def __init__(self, brief: VisualBrief) -> None:
        self.brief = brief
        self.calls = 0

    def plan(
        self,
        workflow_run_id: UUID,
        *,
        draft_title: str,
        draft_deck: str | None,
        draft_body: str,
        locale: str,
        content_format: str,
        vertical_pack: VerticalPack,
        call_key: str,
    ) -> VisualBrief:
        del (
            workflow_run_id,
            draft_title,
            draft_deck,
            draft_body,
            locale,
            content_format,
            vertical_pack,
            call_key,
        )
        self.calls += 1
        return self.brief


class FixtureProvider:
    def __init__(
        self,
        name: str,
        results: dict[str, ProviderAsset],
    ) -> None:
        self.name = name
        self.results = results
        self.calls = 0
        self.idempotency_keys: list[str] = []

    def materialize(
        self,
        workflow_run_id: UUID,
        *,
        draft_id: UUID,
        manifest_input_fingerprint: str,
        spec: VisualAssetSpec,
        vertical_pack: VerticalPack,
        idempotency_key: str,
    ) -> ProviderAsset:
        del (
            workflow_run_id,
            draft_id,
            manifest_input_fingerprint,
            vertical_pack,
        )
        self.calls += 1
        self.idempotency_keys.append(idempotency_key)
        return self.results[spec.slot]


def _text_only_brief() -> VisualBrief:
    return VisualBrief(
        text_only=True,
        rationale="This short explainer does not need a decorative image.",
        art_direction=None,
        assets=[],
    )


def _two_asset_brief() -> VisualBrief:
    return VisualBrief(
        text_only=False,
        rationale="Use a hero illustration plus a sourced reference visual.",
        art_direction="Clean editorial photography/illustration treatment.",
        assets=[
            VisualAssetSpec(
                slot="hero",
                kind=AssetKind.IMAGE,
                purpose="Hero image for the article header.",
                prompt="Editorial illustration of a cloud service launch.",
                alt_text="Illustration representing a cloud service launch.",
                caption="Illustrative visual for the service launch explainer.",
                filename="cloud-service-launch-hero.webp",
                aspect_ratio="16:9",
                variants=[
                    AssetVariantSpec(
                        name="social-square",
                        aspect_ratio="1:1",
                        width=1200,
                        height=1200,
                    )
                ],
            ),
            VisualAssetSpec(
                slot="reference",
                kind=AssetKind.IMAGE,
                purpose="Sourced contextual visual.",
                prompt=None,
                alt_text="Official contextual visual for the service.",
                caption="Context image sourced from the provider's licensed library.",
                filename="cloud-service-reference.webp",
                aspect_ratio="16:9",
                variants=[],
            ),
        ],
    )


def _generated_clear() -> ProviderAsset:
    return ProviderAsset(
        origin=AssetOrigin.GENERATED,
        uri="https://assets.example.test/generated.webp",
        external_id="gen-123",
        mime_type="image/webp",
        aspect_ratio="16:9",
        width=1600,
        height=900,
        source_url=None,
        license_name=None,
        license_url=None,
        rights_status=AssetRightsStatus.CLEAR,
        generation_metadata={
            "model": "fixture-image-model",
            "provider_request_id": "gen-123",
            "terms_basis": "fixture-commercial-use",
        },
        variants=[],
        provenance={"kind": "generated"},
    )


def _external_clear() -> ProviderAsset:
    return ProviderAsset(
        origin=AssetOrigin.EXTERNAL,
        uri="https://assets.example.test/reference.webp",
        external_id="library-456",
        mime_type="image/webp",
        aspect_ratio="16:9",
        width=1600,
        height=900,
        source_url="https://library.example.test/assets/456",
        license_name="Fixture Editorial License",
        license_url="https://library.example.test/license",
        rights_status=AssetRightsStatus.CLEAR,
        generation_metadata={},
        variants=[],
        provenance={"library_asset_id": "456"},
    )


def test_text_only_article_reaches_assets_ready_without_provider() -> None:
    pack = generic_demo_pack()
    draft_id = _create_drafted_run(pack)
    planner = FixturePlanner(_text_only_brief())

    result = CreativeAgent(get_session_factory()).create_manifest(
        draft_id,
        planner=planner,
        provider=None,
    )

    assert result.status is AssetManifestStatus.READY
    assert result.text_only is True
    assert result.rights_status is AssetRightsStatus.CLEAR
    assert result.asset_ids == []
    assert result.workflow_status == WorkflowStatus.ASSETS_READY.value
    assert result.approval_snapshot.assets == []
    assert result.approval_snapshot.draft.version == 1

    with get_session_factory()() as session:
        manifest = session.get(AssetManifest, result.manifest_id)
        assert manifest is not None
        assert manifest.provider_request_count == 0
        asset_count = session.scalar(
            select(func.count())
            .select_from(Asset)
            .where(Asset.manifest_id == manifest.id)
        )
        assert asset_count == 0


def test_generated_and_external_assets_are_distinguishable_with_provenance() -> None:
    pack = generic_demo_pack()
    draft_id = _create_drafted_run(pack)
    planner = FixturePlanner(_two_asset_brief())
    provider = FixtureProvider(
        "fixture-images",
        {
            "hero": _generated_clear(),
            "reference": _external_clear(),
        },
    )

    result = CreativeAgent(get_session_factory()).create_manifest(
        draft_id,
        planner=planner,
        provider=provider,
    )

    assert result.status is AssetManifestStatus.READY
    assert result.rights_status is AssetRightsStatus.CLEAR
    assert len(result.asset_ids) == 2
    assert result.workflow_status == WorkflowStatus.ASSETS_READY.value
    assert provider.calls == 2
    assert len(set(provider.idempotency_keys)) == 2
    assert all(key.startswith("asset:") for key in provider.idempotency_keys)

    with get_session_factory()() as session:
        assets = list(
            session.scalars(
                select(Asset)
                .where(Asset.id.in_(result.asset_ids))
                .order_by(Asset.slot)
            )
        )
        assert len(assets) == 2
        by_slot = {asset.slot: asset for asset in assets}

        hero = by_slot["hero"]
        assert hero.origin == AssetOrigin.GENERATED.value
        assert hero.provider == "fixture-images"
        assert hero.generation_metadata["provider_request_id"] == "gen-123"
        assert hero.generation_metadata["prompt"] is not None
        assert hero.source_url is None

        reference = by_slot["reference"]
        assert reference.origin == AssetOrigin.EXTERNAL.value
        assert reference.source_url == "https://library.example.test/assets/456"
        assert reference.license_name == "Fixture Editorial License"
        assert reference.rights_status == AssetRightsStatus.CLEAR.value

        snapshot_assets = result.approval_snapshot.assets
        assert len(snapshot_assets) == 2
        assert {
            item.version for item in snapshot_assets
        } == {result.manifest_version}
        assert result.approval_snapshot.asset_manifest.version == (
            result.manifest_version
        )


def test_review_required_rights_remain_visible_but_can_reach_assets_ready() -> None:
    pack = generic_demo_pack()
    draft_id = _create_drafted_run(pack)
    brief = VisualBrief(
        text_only=False,
        rationale="Use one sourced contextual image.",
        assets=[
            VisualAssetSpec(
                slot="hero",
                kind=AssetKind.IMAGE,
                purpose="Contextual hero image.",
                prompt=None,
                alt_text="Contextual image.",
                caption="Context image pending rights review.",
                filename="context.webp",
                aspect_ratio="16:9",
            )
        ],
    )
    provider = FixtureProvider(
        "external-library",
        {
            "hero": ProviderAsset(
                origin=AssetOrigin.EXTERNAL,
                uri="https://assets.example.test/context.webp",
                source_url="https://library.example.test/context",
                rights_status=AssetRightsStatus.REVIEW_REQUIRED,
                provenance={"library_asset_id": "context"},
            )
        },
    )

    result = CreativeAgent(get_session_factory()).create_manifest(
        draft_id,
        planner=FixturePlanner(brief),
        provider=provider,
    )

    assert result.status is AssetManifestStatus.REVIEW_REQUIRED
    assert result.rights_status is AssetRightsStatus.REVIEW_REQUIRED
    assert result.workflow_status == WorkflowStatus.ASSETS_READY.value
    assert (
        result.approval_snapshot.asset_manifest.rights_status
        is AssetRightsStatus.REVIEW_REQUIRED
    )


def test_restricted_rights_block_the_workflow() -> None:
    pack = generic_demo_pack()
    draft_id = _create_drafted_run(pack)
    brief = VisualBrief(
        text_only=False,
        rationale="A supplied visual was proposed.",
        assets=[
            VisualAssetSpec(
                slot="hero",
                kind=AssetKind.IMAGE,
                purpose="Hero image.",
                prompt=None,
                alt_text="Provided editorial image.",
                caption="Provided image.",
                filename="provided.webp",
                aspect_ratio="16:9",
            )
        ],
    )
    provider = FixtureProvider(
        "provided-assets",
        {
            "hero": ProviderAsset(
                origin=AssetOrigin.PROVIDED,
                uri="https://assets.example.test/provided.webp",
                rights_status=AssetRightsStatus.RESTRICTED,
                provenance={
                    "provided_by": "fixture-operator",
                    "restriction": "no publication permission",
                },
            )
        },
    )

    result = CreativeAgent(get_session_factory()).create_manifest(
        draft_id,
        planner=FixturePlanner(brief),
        provider=provider,
    )

    assert result.status is AssetManifestStatus.BLOCKED
    assert result.rights_status is AssetRightsStatus.RESTRICTED
    assert result.workflow_status == WorkflowStatus.BLOCKED.value


def test_external_asset_marked_clear_requires_license_metadata() -> None:
    pack = generic_demo_pack()
    draft_id = _create_drafted_run(pack)
    brief = VisualBrief(
        text_only=False,
        rationale="Use one externally sourced image.",
        assets=[
            VisualAssetSpec(
                slot="hero",
                kind=AssetKind.IMAGE,
                purpose="Hero image.",
                prompt=None,
                alt_text="External image.",
                caption="External image.",
                filename="external.webp",
                aspect_ratio="16:9",
            )
        ],
    )
    provider = FixtureProvider(
        "external-library",
        {
            "hero": ProviderAsset(
                origin=AssetOrigin.EXTERNAL,
                uri="https://assets.example.test/external.webp",
                source_url="https://library.example.test/external",
                rights_status=AssetRightsStatus.CLEAR,
                provenance={"asset_id": "external"},
            )
        },
    )

    with pytest.raises(AssetPolicyError):
        CreativeAgent(get_session_factory()).create_manifest(
            draft_id,
            planner=FixturePlanner(brief),
            provider=provider,
        )

    with get_session_factory()() as session:
        draft = session.get(Draft, draft_id)
        assert draft is not None
        run = session.get(WorkflowRun, draft.workflow_run_id)
        assert run is not None
        assert run.status == WorkflowStatus.DRAFTED.value
        count = session.scalar(
            select(func.count())
            .select_from(AssetManifest)
            .where(AssetManifest.draft_id == draft_id)
        )
        assert count == 0


def test_rerun_reuses_manifest_without_duplicate_planner_or_provider_calls() -> None:
    pack = generic_demo_pack()
    draft_id = _create_drafted_run(pack)
    planner = FixturePlanner(_two_asset_brief())
    provider = FixtureProvider(
        "fixture-images",
        {
            "hero": _generated_clear(),
            "reference": _external_clear(),
        },
    )
    agent = CreativeAgent(get_session_factory())

    first = agent.create_manifest(
        draft_id,
        planner=planner,
        provider=provider,
    )
    calls_after_first = (planner.calls, provider.calls)
    second = agent.create_manifest(
        draft_id,
        planner=planner,
        provider=provider,
    )

    assert second.manifest_id == first.manifest_id
    assert second.asset_ids == first.asset_ids
    assert (planner.calls, provider.calls) == calls_after_first

    with get_session_factory()() as session:
        manifest_count = session.scalar(
            select(func.count())
            .select_from(AssetManifest)
            .where(AssetManifest.draft_id == draft_id)
        )
        asset_count = session.scalar(
            select(func.count())
            .select_from(Asset)
            .where(Asset.manifest_id == first.manifest_id)
        )
        assert manifest_count == 1
        assert asset_count == 2


def test_provider_is_swappable_without_core_branching() -> None:
    pack = generic_demo_pack()
    brief = VisualBrief(
        text_only=False,
        rationale="Use one generated hero image.",
        assets=[
            VisualAssetSpec(
                slot="hero",
                kind=AssetKind.IMAGE,
                purpose="Hero image.",
                prompt="Abstract cloud systems illustration.",
                alt_text="Abstract cloud systems illustration.",
                caption="Illustrative cloud systems visual.",
                filename="cloud.webp",
                aspect_ratio="16:9",
            )
        ],
    )

    first_draft = _create_drafted_run(pack)
    second_draft = _create_drafted_run(pack)
    first_provider = FixtureProvider(
        "provider-a",
        {"hero": _generated_clear()},
    )
    second_asset = _generated_clear().model_copy(
        update={
            "uri": "https://assets.example.test/provider-b.webp",
            "external_id": "provider-b-1",
            "generation_metadata": {
                "model": "provider-b-model",
                "provider_request_id": "provider-b-1",
            },
        }
    )
    second_provider = FixtureProvider(
        "provider-b",
        {"hero": second_asset},
    )
    agent = CreativeAgent(get_session_factory())

    first = agent.create_manifest(
        first_draft,
        planner=FixturePlanner(brief),
        provider=first_provider,
    )
    second = agent.create_manifest(
        second_draft,
        planner=FixturePlanner(brief),
        provider=second_provider,
    )

    with get_session_factory()() as session:
        asset_a = session.get(Asset, first.asset_ids[0])
        asset_b = session.get(Asset, second.asset_ids[0])
        assert asset_a is not None
        assert asset_b is not None
        assert asset_a.provider == "provider-a"
        assert asset_b.provider == "provider-b"


def test_vertical_visual_rules_are_enforced() -> None:
    base = generic_demo_pack()
    required = base.model_copy(
        update={
            "visual": base.visual.model_copy(
                update={
                    "assets_required": True,
                    "max_assets": 1,
                }
            )
        }
    )
    draft_id = _create_drafted_run(required)
    agent = CreativeAgent(get_session_factory())

    with pytest.raises(VisualBriefValidationError):
        agent.create_manifest(
            draft_id,
            planner=FixturePlanner(_text_only_brief()),
        )

    too_many = _two_asset_brief()
    with pytest.raises(VisualBriefValidationError):
        agent.create_manifest(
            draft_id,
            planner=FixturePlanner(too_many),
            provider=FixtureProvider(
                "unused",
                {
                    "hero": _generated_clear(),
                    "reference": _external_clear(),
                },
            ),
        )
