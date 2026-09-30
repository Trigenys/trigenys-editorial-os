from __future__ import annotations

import json
from uuid import UUID

from editorial_os_api.editorial_qa.contracts import (
    QAAssetContext,
    QAClaimContext,
    QADraftContext,
    SemanticQAOutput,
)
from editorial_os_api.model_gateway import (
    ModelGateway,
    ModelMessage,
    ModelRequest,
    ModelRole,
    ModelTask,
)
from editorial_os_api.vertical_packs import VerticalPack


class ModelEditorialQAAdapter:
    name = "model-gateway"

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

    def review(
        self,
        workflow_run_id: UUID,
        *,
        draft: QADraftContext,
        claims: list[QAClaimContext],
        assets: list[QAAssetContext],
        vertical_pack: VerticalPack,
        call_key: str,
    ) -> SemanticQAOutput:
        payload = {
            "draft": draft.model_dump(mode="json"),
            "claims": [item.model_dump(mode="json") for item in claims],
            "assets": [item.model_dump(mode="json") for item in assets],
            "voice_rules": vertical_pack.voice.model_dump(mode="json"),
            "visual_rules": vertical_pack.visual.model_dump(mode="json"),
        }
        request = ModelRequest(
            workflow_run_id=workflow_run_id,
            agent_id="editorial-qa",
            task=ModelTask.EDITORIAL_QA,
            messages=[
                ModelMessage(
                    role=ModelRole.SYSTEM,
                    content=(
                        "Perform editorial consistency checks only. The deterministic "
                        "policy engine owns factual support, risk, rights and workflow "
                        "decisions. Return structured findings for misleading headline/body "
                        "relationships, material internal contradictions, asset/text mismatch, "
                        "or quality/style defects not already represented by the supplied "
                        "vertical rules. Do not invent facts, sources, evidence or policy. "
                        "Use WARNING for a review note and ERROR for a revision-worthy defect."
                    ),
                ),
                ModelMessage(
                    role=ModelRole.USER,
                    content=json.dumps(payload, sort_keys=True),
                ),
            ],
            max_output_tokens=2500,
            temperature=0.0,
        )
        return self._gateway.generate_structured(
            request,
            SemanticQAOutput,
            call_key=call_key,
        )
