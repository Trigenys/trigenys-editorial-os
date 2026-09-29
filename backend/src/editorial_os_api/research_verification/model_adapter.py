from __future__ import annotations

import json
from uuid import UUID

from editorial_os_api.model_gateway import (
    ModelGateway,
    ModelMessage,
    ModelRequest,
    ModelRole,
    ModelTask,
)
from editorial_os_api.research_verification.contracts import (
    ClaimPlanOutput,
    ClaimSeed,
    ResearchSourceDocument,
    SourceAssessmentOutput,
)


class ModelResearchAdapter:
    name = "model-gateway"

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

    def plan_claims(
        self,
        workflow_run_id: UUID,
        *,
        candidate_title: str,
        candidate_angle: str,
        sources: list[ResearchSourceDocument],
        max_claims: int,
        call_key: str,
    ) -> list[ClaimSeed]:
        source_context = [
            {
                "source_item_id": str(source.source_item_id),
                "title": source.title,
                "url": source.url,
                "source_role": source.source_role.value,
                "evidence_tier": source.evidence_tier.value,
                "text": source.text[:6000],
            }
            for source in sources
        ]
        request = ModelRequest(
            workflow_run_id=workflow_run_id,
            agent_id="research-verification",
            task=ModelTask.RESEARCH_VERIFICATION,
            messages=[
                ModelMessage(
                    role=ModelRole.SYSTEM,
                    content=(
                        "Extract a bounded list of canonical factual claims to verify. "
                        "Do not mark any claim true or assign confidence. claim_key values "
                        "must be stable lowercase identifiers using letters, digits, dot, "
                        "underscore, colon or hyphen only."
                    ),
                ),
                ModelMessage(
                    role=ModelRole.USER,
                    content=json.dumps(
                        {
                            "candidate_title": candidate_title,
                            "candidate_angle": candidate_angle,
                            "max_claims": max_claims,
                            "sources": source_context,
                        },
                        sort_keys=True,
                    ),
                ),
            ],
            max_output_tokens=1600,
            temperature=0,
        )
        output = self._gateway.generate_structured(
            request,
            ClaimPlanOutput,
            call_key=call_key,
        )
        return output.claims

    def assess_source(
        self,
        workflow_run_id: UUID,
        *,
        source: ResearchSourceDocument,
        claims: list[ClaimSeed],
        call_key: str,
    ) -> SourceAssessmentOutput:
        request = ModelRequest(
            workflow_run_id=workflow_run_id,
            agent_id="research-verification",
            task=ModelTask.RESEARCH_VERIFICATION,
            messages=[
                ModelMessage(
                    role=ModelRole.SYSTEM,
                    content=(
                        "Assess only the supplied source against the supplied canonical claims. "
                        "For SUPPORTS, REFUTES or CONTEXT, excerpt must be copied verbatim from "
                        "the source text. If the source does not directly support an assessment, "
                        "use NO_EVIDENCE. Do not assign confidence or evidence tier."
                    ),
                ),
                ModelMessage(
                    role=ModelRole.USER,
                    content=json.dumps(
                        {
                            "source": {
                                "url": source.url,
                                "title": source.title,
                                "text": source.text[:12000],
                            },
                            "claims": [
                                {
                                    "claim_key": claim.claim_key,
                                    "statement": claim.statement,
                                }
                                for claim in claims
                            ],
                        },
                        sort_keys=True,
                    ),
                ),
            ],
            max_output_tokens=2200,
            temperature=0,
        )
        return self._gateway.generate_structured(
            request,
            SourceAssessmentOutput,
            call_key=call_key,
        )
