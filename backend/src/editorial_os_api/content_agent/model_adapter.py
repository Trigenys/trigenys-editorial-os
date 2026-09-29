from __future__ import annotations

import json
from uuid import UUID

from editorial_os_api.content_agent.contracts import (
    ContentAdapter,
    ContentClaimContext,
    ContentDraftOutput,
)
from editorial_os_api.model_gateway import (
    ModelGateway,
    ModelMessage,
    ModelRequest,
    ModelRole,
    ModelTask,
)
from editorial_os_api.vertical_packs import VerticalPack


class ModelContentAdapter(ContentAdapter):
    name = "model-gateway"

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

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
        return self._complete(
            workflow_run_id,
            claims=claims,
            vertical_pack=vertical_pack,
            locale=locale,
            content_format=content_format,
            angle=angle,
            call_key=call_key,
            previous=None,
            feedback=None,
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
        return self._complete(
            workflow_run_id,
            claims=claims,
            vertical_pack=vertical_pack,
            locale=locale,
            content_format=content_format,
            angle=angle,
            call_key=call_key,
            previous=previous,
            feedback=feedback,
        )

    def _complete(
        self,
        workflow_run_id: UUID,
        *,
        claims: list[ContentClaimContext],
        vertical_pack: VerticalPack,
        locale: str,
        content_format: str,
        angle: str,
        call_key: str,
        previous: ContentDraftOutput | None,
        feedback: str | None,
    ) -> ContentDraftOutput:
        claim_payload = [
            {
                **claim.model_dump(mode="json"),
                "evidence": [
                    {
                        "evidence_id": str(reference.evidence_id),
                        "url": (
                            reference.url
                            if vertical_pack.source_rules.include_source_urls_in_prompt
                            else None
                        ),
                        "tier": reference.tier,
                    }
                    for reference in claim.evidence
                ],
            }
            for claim in claims
        ]
        user_payload: dict[str, object] = {
            "angle": angle,
            "locale": locale,
            "content_format": content_format,
            "audience": vertical_pack.audience,
            "voice": vertical_pack.voice.model_dump(mode="json"),
            "seo_rules": vertical_pack.seo.model_dump(mode="json"),
            "internal_link_topics": vertical_pack.internal_link_topics,
            "verified_claims": claim_payload,
        }
        if previous is not None:
            user_payload["previous_draft"] = previous.model_dump(mode="json")
            user_payload["operator_feedback"] = feedback

        request = ModelRequest(
            workflow_run_id=workflow_run_id,
            agent_id="content",
            task=ModelTask.CONTENT_DRAFTING,
            messages=[
                ModelMessage(
                    role=ModelRole.SYSTEM,
                    content=(
                        "Write only from the supplied verified claim ledger. "
                        "Every factual assertion in every section must be listed in that "
                        "section's factual_assertions. Use the matching claim_key when the "
                        "assertion is supported by the ledger. If you introduce a factual "
                        "assertion that is not in the ledger, set claim_key to null so the "
                        "system can mark it unsupported. Do not browse, invent citations, "
                        "or create source facts outside the supplied context."
                    ),
                ),
                ModelMessage(
                    role=ModelRole.USER,
                    content=json.dumps(user_payload, sort_keys=True),
                ),
            ],
            max_output_tokens=5000,
            temperature=0.4,
        )
        return self._gateway.generate_structured(
            request,
            ContentDraftOutput,
            call_key=call_key,
        )
