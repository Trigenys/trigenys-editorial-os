from __future__ import annotations

import json
from uuid import UUID

from editorial_os_api.creative_agent.contracts import VisualBrief
from editorial_os_api.model_gateway import (
    ModelGateway,
    ModelMessage,
    ModelRequest,
    ModelRole,
    ModelTask,
)
from editorial_os_api.vertical_packs import VerticalPack


class ModelCreativePlanner:
    name = "model-gateway"

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

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
        payload = {
            "draft": {
                "title": draft_title,
                "deck": draft_deck,
                "body": draft_body[:12_000],
                "locale": locale,
                "content_format": content_format,
            },
            "visual_rules": vertical_pack.visual.model_dump(mode="json"),
            "audience": vertical_pack.audience,
        }
        request = ModelRequest(
            workflow_run_id=workflow_run_id,
            agent_id="creative",
            task=ModelTask.CREATIVE_BRIEF,
            messages=[
                ModelMessage(
                    role=ModelRole.SYSTEM,
                    content=(
                        "Create a visual brief, not an image. Respect the supplied visual "
                        "rules. A text-only article is valid when assets are optional. "
                        "Do not claim a generated or selected image is authentic evidence "
                        "of a real event/person. Filenames must be safe ASCII slugs with "
                        "extensions. Alt text and captions must describe the intended "
                        "editorial use without inventing factual details."
                    ),
                ),
                ModelMessage(
                    role=ModelRole.USER,
                    content=json.dumps(payload, sort_keys=True),
                ),
            ],
            max_output_tokens=2400,
            temperature=0.2,
        )
        return self._gateway.generate_structured(
            request,
            VisualBrief,
            call_key=call_key,
        )
