from __future__ import annotations

import json
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from editorial_os_api.creative_agent.contracts import (
    AssetProvider,
    CreativeAgentResult,
    CreativePlanner,
    GateBApprovalSnapshot,
    ProviderAsset,
    VisualAssetSpec,
    VisualBrief,
)
from editorial_os_api.domain.enums import (
    AssetManifestStatus,
    AssetOrigin,
    AssetRightsStatus,
    AuditActorKind,
    WorkflowActionType,
    WorkflowStatus,
)
from editorial_os_api.observability import ObservabilityHub, ProductTelemetryEvent
from editorial_os_api.orchestration import PostgresWorkflowEngine, WorkflowCommand
from editorial_os_api.persistence.base import utcnow
from editorial_os_api.persistence.models import (
    Asset,
    AssetManifest,
    AuditEvent,
    Draft,
    WorkflowRun,
)
from editorial_os_api.vertical_packs import VerticalPack


class CreativeAgentError(RuntimeError):
    pass


class VisualBriefValidationError(CreativeAgentError):
    pass


class AssetPolicyError(CreativeAgentError):
    pass


_RIGHTS_RANK = {
    AssetRightsStatus.CLEAR: 0,
    AssetRightsStatus.REVIEW_REQUIRED: 1,
    AssetRightsStatus.RESTRICTED: 2,
}


class CreativeAgent:
    agent_id = "creative"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        workflow_engine: PostgresWorkflowEngine | None = None,
        observability: ObservabilityHub | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._workflow_engine = workflow_engine or PostgresWorkflowEngine(
            session_factory
        )
        self._observability = observability or ObservabilityHub()

    def create_manifest(
        self,
        draft_id: UUID,
        *,
        planner: CreativePlanner,
        provider: AssetProvider | None = None,
    ) -> CreativeAgentResult:
        with self._session_factory() as session:
            draft = session.get(Draft, draft_id)
            if draft is None:
                raise CreativeAgentError(f"Unknown draft: {draft_id}")
            run = session.get(WorkflowRun, draft.workflow_run_id)
            if run is None:
                raise CreativeAgentError("Draft workflow run no longer exists.")

            pack = self._load_pack(draft)
            provider_name = provider.name if provider is not None else "none"
            fingerprint = self._input_fingerprint(
                draft=draft,
                vertical_pack=pack,
                planner_name=planner.name,
                provider_name=provider_name,
            )
            existing = session.scalar(
                select(AssetManifest).where(
                    AssetManifest.workflow_run_id == draft.workflow_run_id,
                    AssetManifest.draft_id == draft.id,
                    AssetManifest.input_fingerprint == fingerprint,
                )
            )
            if existing is not None:
                self._handoff(existing)
                return self._result(existing)

            if WorkflowStatus(run.status) is not WorkflowStatus.DRAFTED:
                raise CreativeAgentError(
                    "A new asset manifest requires workflow status DRAFTED."
                )

            workflow_run_id = draft.workflow_run_id
            draft_title = draft.title
            draft_deck = draft.deck
            draft_body = draft.body
            draft_locale = draft.locale
            content_format = draft.content_format
            draft_version = draft.version

        visual_brief = planner.plan(
            workflow_run_id,
            draft_title=draft_title,
            draft_deck=draft_deck,
            draft_body=draft_body,
            locale=draft_locale,
            content_format=content_format,
            vertical_pack=pack,
            call_key=f"creative-plan:{draft_id}:v{draft_version}:{fingerprint[:20]}",
        )
        self._validate_visual_brief(visual_brief, pack)

        provider_results: list[tuple[VisualAssetSpec, ProviderAsset]] = []
        if not visual_brief.text_only:
            if provider is None:
                raise AssetPolicyError(
                    "A non-text-only visual brief requires an asset provider."
                )
            for spec in visual_brief.assets:
                result = provider.materialize(
                    workflow_run_id,
                    draft_id=draft_id,
                    manifest_input_fingerprint=fingerprint,
                    spec=spec,
                    vertical_pack=pack,
                    idempotency_key=f"asset:{fingerprint}:{spec.slot}",
                )
                self._validate_provider_asset(
                    result,
                    spec=spec,
                    vertical_pack=pack,
                )
                provider_results.append((spec, result))

        rights_status = self._aggregate_rights(
            [result.rights_status for _, result in provider_results]
        )
        manifest_status = self._manifest_status(
            text_only=visual_brief.text_only,
            rights_status=rights_status,
        )

        with self._session_factory.begin() as session:
            version = (
                session.scalar(
                    select(func.max(AssetManifest.version)).where(
                        AssetManifest.workflow_run_id == workflow_run_id,
                        AssetManifest.draft_id == draft_id,
                    )
                )
                or 0
            ) + 1
            manifest = AssetManifest(
                workflow_run_id=workflow_run_id,
                draft_id=draft_id,
                version=version,
                input_fingerprint=fingerprint,
                status=manifest_status.value,
                text_only=visual_brief.text_only,
                rights_status=rights_status.value,
                provider_name=(
                    provider.name
                    if provider is not None and provider_results
                    else None
                ),
                provider_request_count=len(provider_results),
                visual_brief=visual_brief.model_dump(mode="json"),
                asset_ids=[],
                approval_snapshot={},
                vertical_pack_snapshot=pack.model_dump(mode="json"),
            )
            session.add(manifest)
            session.flush()

            persisted_assets: list[Asset] = []
            for spec, result in provider_results:
                asset = Asset(
                    workflow_run_id=workflow_run_id,
                    manifest_id=manifest.id,
                    version=manifest.version,
                    slot=spec.slot,
                    kind=spec.kind.value,
                    origin=result.origin.value,
                    provider=provider.name if provider is not None else "none",
                    uri=result.uri,
                    external_id=result.external_id,
                    filename=spec.filename,
                    mime_type=result.mime_type,
                    aspect_ratio=result.aspect_ratio or spec.aspect_ratio,
                    width=result.width,
                    height=result.height,
                    source_url=result.source_url,
                    license_name=result.license_name,
                    license_url=result.license_url,
                    rights_status=result.rights_status.value,
                    alt_text=spec.alt_text,
                    caption=spec.caption,
                    generation_metadata={
                        **result.generation_metadata,
                        "prompt": spec.prompt,
                    },
                    variants=result.variants
                    or [
                        variant.model_dump(mode="json")
                        for variant in spec.variants
                    ],
                    provenance={
                        **result.provenance,
                        "visual_purpose": spec.purpose,
                        "manifest_input_fingerprint": fingerprint,
                    },
                    owner_key=f"asset:{fingerprint}:{spec.slot}",
                )
                session.add(asset)
                session.flush()
                persisted_assets.append(asset)

            manifest.asset_ids = [str(asset.id) for asset in persisted_assets]
            manifest.approval_snapshot = self._approval_snapshot(
                draft_id=draft_id,
                draft_version=draft_version,
                manifest=manifest,
                assets=persisted_assets,
            )
            session.add(
                AuditEvent(
                    workflow_run_id=workflow_run_id,
                    actor_kind=AuditActorKind.AGENT.value,
                    actor_id=self.agent_id,
                    event_type="creative.asset_manifest.created",
                    entity_type="asset_manifest",
                    entity_id=manifest.id,
                    occurred_at=utcnow(),
                    payload={
                        "manifest_version": manifest.version,
                        "draft_id": str(draft_id),
                        "draft_version": draft_version,
                        "text_only": manifest.text_only,
                        "status": manifest.status,
                        "rights_status": manifest.rights_status,
                        "asset_ids": list(manifest.asset_ids),
                    },
                )
            )
            manifest_id = manifest.id

        with self._session_factory() as session:
            persisted = session.get(AssetManifest, manifest_id)
            assert persisted is not None
            self._handoff(persisted)

        self._observability.record_product_event(
            ProductTelemetryEvent(
                event_name="creative asset manifest created",
                workflow_run_id=workflow_run_id,
                agent_id=self.agent_id,
                properties={
                    "manifest_id": str(manifest_id),
                    "manifest_status": manifest_status.value,
                    "rights_status": rights_status.value,
                    "text_only": visual_brief.text_only,
                    "asset_count": len(provider_results),
                    "provider": (
                        provider.name if provider is not None else "none"
                    ),
                },
            )
        )

        with self._session_factory() as session:
            persisted = session.get(AssetManifest, manifest_id)
            assert persisted is not None
            return self._result(persisted)

    def approval_snapshot(self, manifest_id: UUID) -> GateBApprovalSnapshot:
        with self._session_factory() as session:
            manifest = session.get(AssetManifest, manifest_id)
            if manifest is None:
                raise CreativeAgentError(
                    f"Unknown asset manifest: {manifest_id}"
                )
            return GateBApprovalSnapshot.model_validate(
                manifest.approval_snapshot
            )

    @staticmethod
    def _load_pack(draft: Draft) -> VerticalPack:
        try:
            return VerticalPack.model_validate(draft.vertical_pack_snapshot)
        except Exception as exc:
            raise CreativeAgentError(
                "Draft has no valid versioned vertical-pack snapshot."
            ) from exc

    @staticmethod
    def _validate_visual_brief(
        brief: VisualBrief,
        vertical_pack: VerticalPack,
    ) -> None:
        rules = vertical_pack.visual
        if brief.text_only:
            if rules.assets_required:
                raise VisualBriefValidationError(
                    "Vertical pack requires assets; text-only is not allowed."
                )
            return

        if len(brief.assets) > rules.max_assets:
            raise VisualBriefValidationError(
                "Visual brief exceeds vertical-pack asset limit."
            )

        allowed_kinds = set(rules.allowed_kinds)
        allowed_ratios = set(rules.allowed_aspect_ratios)
        for spec in brief.assets:
            if spec.kind.value not in allowed_kinds:
                raise VisualBriefValidationError(
                    f"Asset kind {spec.kind.value!r} is not allowed."
                )
            if spec.aspect_ratio not in allowed_ratios:
                raise VisualBriefValidationError(
                    f"Aspect ratio {spec.aspect_ratio!r} is not allowed."
                )
            if rules.require_alt_text and not (spec.alt_text or "").strip():
                raise VisualBriefValidationError(
                    f"Asset slot {spec.slot!r} requires alt text."
                )
            if rules.require_caption and not (spec.caption or "").strip():
                raise VisualBriefValidationError(
                    f"Asset slot {spec.slot!r} requires a caption."
                )
            for variant in spec.variants:
                if variant.aspect_ratio not in allowed_ratios:
                    raise VisualBriefValidationError(
                        f"Variant ratio {variant.aspect_ratio!r} is not allowed."
                    )

    @staticmethod
    def _validate_provider_asset(
        result: ProviderAsset,
        *,
        spec: VisualAssetSpec,
        vertical_pack: VerticalPack,
    ) -> None:
        if result.uri is None or not result.uri.strip():
            raise AssetPolicyError(
                f"Asset provider returned no URI for slot {spec.slot!r}."
            )

        rules = vertical_pack.visual
        if result.origin is AssetOrigin.GENERATED:
            if not rules.allow_generated_assets:
                raise AssetPolicyError(
                    "Vertical pack forbids generated assets."
                )
            if not result.generation_metadata:
                raise AssetPolicyError(
                    "Generated assets require generation metadata."
                )
        elif result.origin is AssetOrigin.EXTERNAL:
            if not rules.allow_external_assets:
                raise AssetPolicyError(
                    "Vertical pack forbids externally sourced assets."
                )
            if not (result.source_url or "").strip():
                raise AssetPolicyError(
                    "External assets require a source URL."
                )
            if (
                result.rights_status is AssetRightsStatus.CLEAR
                and not (
                    (result.license_name or "").strip()
                    or (result.license_url or "").strip()
                )
            ):
                raise AssetPolicyError(
                    "External assets marked CLEAR require license metadata."
                )
        elif result.origin is AssetOrigin.PROVIDED:
            if not result.provenance:
                raise AssetPolicyError(
                    "Provided assets require provenance metadata."
                )

        ratio = result.aspect_ratio or spec.aspect_ratio
        if ratio not in set(rules.allowed_aspect_ratios):
            raise AssetPolicyError(
                f"Provider asset ratio {ratio!r} is not allowed."
            )

    @staticmethod
    def _aggregate_rights(
        statuses: list[AssetRightsStatus],
    ) -> AssetRightsStatus:
        if not statuses:
            return AssetRightsStatus.CLEAR
        return max(statuses, key=lambda status: _RIGHTS_RANK[status])

    @staticmethod
    def _manifest_status(
        *,
        text_only: bool,
        rights_status: AssetRightsStatus,
    ) -> AssetManifestStatus:
        if rights_status is AssetRightsStatus.RESTRICTED:
            return AssetManifestStatus.BLOCKED
        if rights_status is AssetRightsStatus.REVIEW_REQUIRED:
            return AssetManifestStatus.REVIEW_REQUIRED
        if text_only or rights_status is AssetRightsStatus.CLEAR:
            return AssetManifestStatus.READY
        raise AssertionError("Unhandled manifest status.")

    @staticmethod
    def _input_fingerprint(
        *,
        draft: Draft,
        vertical_pack: VerticalPack,
        planner_name: str,
        provider_name: str,
    ) -> str:
        payload = {
            "draft_id": str(draft.id),
            "draft_version": draft.version,
            "draft_fingerprint": draft.input_fingerprint,
            "vertical_pack": vertical_pack.model_dump(mode="json"),
            "planner": planner_name,
            "provider": provider_name,
        }
        return sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _approval_snapshot(
        *,
        draft_id: UUID,
        draft_version: int,
        manifest: AssetManifest,
        assets: list[Asset],
    ) -> dict[str, object]:
        return {
            "draft": {
                "id": str(draft_id),
                "version": draft_version,
            },
            "asset_manifest": {
                "id": str(manifest.id),
                "version": manifest.version,
                "status": manifest.status,
                "rights_status": manifest.rights_status,
                "text_only": manifest.text_only,
            },
            "assets": [
                {
                    "id": str(asset.id),
                    "version": asset.version,
                    "slot": asset.slot,
                    "kind": asset.kind,
                    "origin": asset.origin,
                    "rights_status": asset.rights_status,
                    "filename": asset.filename,
                }
                for asset in assets
            ],
        }

    def _handoff(self, manifest: AssetManifest) -> None:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, manifest.workflow_run_id)
            if run is None:
                raise CreativeAgentError(
                    "Asset manifest workflow run no longer exists."
                )
            status = WorkflowStatus(run.status)

        manifest_status = AssetManifestStatus(manifest.status)
        if manifest_status is AssetManifestStatus.BLOCKED:
            if status is WorkflowStatus.BLOCKED:
                return
            if status is not WorkflowStatus.DRAFTED:
                raise CreativeAgentError(
                    "Blocked asset manifest can only hand off from DRAFTED."
                )
            self._workflow_engine.apply(
                manifest.workflow_run_id,
                WorkflowCommand(
                    action_key=(
                        f"creative-block:{manifest.id}:v{manifest.version}"
                    ),
                    action_type=WorkflowActionType.BLOCK,
                    actor_kind=AuditActorKind.AGENT,
                    actor_id=self.agent_id,
                    payload={
                        "asset_manifest_id": str(manifest.id),
                        "asset_manifest_version": manifest.version,
                        "rights_status": manifest.rights_status,
                        "approval_snapshot": manifest.approval_snapshot,
                    },
                ),
            )
            return

        if status is WorkflowStatus.ASSETS_READY:
            return
        if status is not WorkflowStatus.DRAFTED:
            raise CreativeAgentError(
                "Asset manifest handoff is only legal from DRAFTED."
            )
        self._workflow_engine.apply(
            manifest.workflow_run_id,
            WorkflowCommand(
                action_key=f"assets-ready:{manifest.id}:v{manifest.version}",
                action_type=WorkflowActionType.ASSETS_COMPLETED,
                actor_kind=AuditActorKind.AGENT,
                actor_id=self.agent_id,
                payload={
                    "asset_manifest_id": str(manifest.id),
                    "asset_manifest_version": manifest.version,
                    "manifest_status": manifest.status,
                    "rights_status": manifest.rights_status,
                    "text_only": manifest.text_only,
                    "asset_ids": list(manifest.asset_ids),
                    "approval_snapshot": manifest.approval_snapshot,
                },
            ),
        )

    def _result(self, manifest: AssetManifest) -> CreativeAgentResult:
        with self._session_factory() as session:
            run = session.get(WorkflowRun, manifest.workflow_run_id)
            draft = session.get(Draft, manifest.draft_id)
            if run is None or draft is None:
                raise CreativeAgentError(
                    "Asset manifest references missing workflow or draft."
                )
            workflow_status = run.status
            draft_version = draft.version

        return CreativeAgentResult(
            workflow_run_id=manifest.workflow_run_id,
            draft_id=manifest.draft_id,
            draft_version=draft_version,
            manifest_id=manifest.id,
            manifest_version=manifest.version,
            status=AssetManifestStatus(manifest.status),
            text_only=manifest.text_only,
            rights_status=AssetRightsStatus(manifest.rights_status),
            asset_ids=[UUID(value) for value in manifest.asset_ids],
            approval_snapshot=GateBApprovalSnapshot.model_validate(
                manifest.approval_snapshot
            ),
            workflow_status=workflow_status,
        )
