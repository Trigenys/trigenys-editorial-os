"""Gate-respecting Mukuru staging pilot: inspect, enrich sources, then draft.

The canonical state belongs to WorkflowEngine. This script never forges Gate A,
B or C decisions and never calls the publishing adapter. AI calls are opt-in via
a manually dispatched GitHub Action with a bounded model budget.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from editorial_os_api.config import Settings
from editorial_os_api.content_agent import ContentAgent, ModelContentAdapter
from editorial_os_api.domain.enums import GateKind, GateOutcome, WorkflowStatus
from editorial_os_api.model_gateway import (
    BudgetLedger,
    BudgetPolicy,
    ModelGateway,
    ModelPolicy,
    ModelRoute,
    ModelTask,
)
from editorial_os_api.model_gateway.adapters.litellm import LiteLLMClient
from editorial_os_api.persistence.models import (
    GateDecision,
    Source,
    SourceItem,
    TopicCandidate,
    WorkflowRun,
)
from editorial_os_api.persistence.session import get_session_factory
from editorial_os_api.research_verification import (
    ModelResearchAdapter,
    ResearchBudget,
    ResearchVerificationAgent,
    VerificationPolicy,
)
from editorial_os_api.scout import ScoutAgent
from editorial_os_api.scout.adapters.manual import HttpPageExtractor
from editorial_os_api.scout.contracts import ManualUrlInput
from editorial_os_api.vertical_packs.builtin import get_builtin_vertical_pack
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

RUN_ID = UUID("13624834-42e5-46e7-bda9-f1a5da72cd44")
EXPECTED_TITLE = "The 20-metre neobank: How Mukuru is solving the gap between receiving cash and spending it"
OFFICIAL_SOURCES = {
    "GSMA": "https://www.gsma.com/sotir/",
    "World Bank Cameroon": (
        "https://www.worldbank.org/en/news/press-release/2025/07/16/"
        "mobile-phone-technology-powers-saving-surge-in-developing-economies"
    ),
}
MAX_COST_USD = Decimal("0.50")


@dataclass(frozen=True)
class PilotPreflight:
    workflow_status: str
    topic_title: str
    gate_a_approved: bool
    original_sources: int
    independent_official_sources: int
    usable_official_sources: int
    additional_source_item_ids: tuple[UUID, ...]

    @property
    def can_draft(self) -> bool:
        return (
            self.gate_a_approved
            and self.workflow_status == WorkflowStatus.TOPIC_APPROVED.value
            and self.independent_official_sources >= 2
            and self.usable_official_sources >= 2
        )


def source_usable(body: object) -> bool:
    """Require substantive extracted text, not an RSS title/teaser."""
    return isinstance(body, str) and len(body.strip()) >= 500


def _source_text(item: SourceItem) -> str:
    payload = item.extracted_payload or {}
    text = payload.get("body")
    return text if isinstance(text, str) else ""


def preflight(sessions: sessionmaker[Session]) -> PilotPreflight:
    with sessions() as session:
        run = session.get(WorkflowRun, RUN_ID)
        if run is None:
            raise RuntimeError("Mukuru pilot workflow run is absent.")
        if run.vertical_key != "trigenys-insight":
            raise RuntimeError("Unexpected vertical; refusing to modify another workflow.")
        pack = get_builtin_vertical_pack(run.vertical_key, run.vertical_version)
        if not pack.supports(locale="fr", content_format="article"):
            raise RuntimeError("Live vertical pack cannot generate a French article.")
        topic = session.scalar(
            select(TopicCandidate)
            .where(TopicCandidate.workflow_run_id == RUN_ID)
            .order_by(TopicCandidate.version.desc())
            .limit(1)
        )
        if topic is None or topic.title != EXPECTED_TITLE:
            raise RuntimeError("Mukuru canonical candidate mismatch.")
        approved = session.scalar(
            select(GateDecision)
            .where(
                GateDecision.workflow_run_id == RUN_ID,
                GateDecision.gate == GateKind.TOPIC.value,
                GateDecision.outcome == GateOutcome.APPROVED.value,
                GateDecision.artifact_id == topic.id,
                GateDecision.artifact_version == topic.version,
            )
            .order_by(GateDecision.decided_at.desc())
            .limit(1)
        ) is not None
        official_items = []
        for name, requested_url in OFFICIAL_SOURCES.items():
            source = session.scalar(select(Source).where(Source.name == name))
            if source is None:
                continue
            # Source records are owned by Scout; locate only the exact
            # approved URL, never unrelated articles under the same publisher.
            item = session.scalar(
                select(SourceItem)
                .where(
                    SourceItem.source_id == source.id,
                    SourceItem.canonical_url == requested_url.rstrip("/"),
                )
                .order_by(SourceItem.observed_at.desc())
                .limit(1)
            )
            if item is None:
                item = session.scalar(
                    select(SourceItem)
                    .where(
                        SourceItem.source_id == source.id,
                        SourceItem.canonical_url == requested_url,
                    )
                    .order_by(SourceItem.observed_at.desc())
                    .limit(1)
                )
            if item is not None:
                official_items.append(item)
        return PilotPreflight(
            workflow_status=run.status,
            topic_title=topic.title,
            gate_a_approved=approved,
            original_sources=len(topic.source_item_ids),
            independent_official_sources=len(official_items),
            usable_official_sources=sum(
                source_usable(_source_text(item)) for item in official_items
            ),
            additional_source_item_ids=tuple(item.id for item in official_items),
        )


def report(snapshot: PilotPreflight) -> dict[str, Any]:
    return {
        "workflow_run_id": str(RUN_ID),
        "title": snapshot.topic_title,
        "workflow_status": snapshot.workflow_status,
        "gate_a_approved": snapshot.gate_a_approved,
        "original_source_items": snapshot.original_sources,
        "official_source_items": snapshot.independent_official_sources,
        "official_sources_with_usable_text": snapshot.usable_official_sources,
        "can_generate_verified_draft": snapshot.can_draft,
        "next": (
            "Research and French drafting are permitted."
            if snapshot.can_draft else
            "Source enrichment and explicit Gate A human approval are required."
        ),
        "publication_allowed": False,
    }


def enrich(sessions: sessionmaker[Session]) -> None:
    """Fetch two fixed institutional references, without touching human gates."""
    scout = ScoutAgent(sessions)
    extractor = HttpPageExtractor()
    for name, url in OFFICIAL_SOURCES.items():
        with sessions() as session:
            source = session.scalar(select(Source).where(Source.name == name))
            if source is None or not source.enabled:
                raise RuntimeError(f"Approved source {name!r} is absent or disabled.")
            source_id = source.id
        result = scout.ingest_manual_url(
            source_id,
            ManualUrlInput(url=url, locale="en"),
            extractor=extractor,
            force=True,
        )
        if result.status != "SUCCEEDED":
            raise RuntimeError(
                f"Official source {name!r} ingestion failed: {result.failure_kind}"
            )
        print(json.dumps({
            "source": name,
            "status": result.status,
            "created": result.created_count,
            "updated": result.updated_count,
        }))


def draft(sessions: sessionmaker[Session], snapshot: PilotPreflight) -> None:
    if not snapshot.can_draft:
        raise RuntimeError("Fail closed: no verified human Gate A or insufficient official sources.")

    model = os.environ.get("EDITORIAL_PILOT_MODEL", "").strip()
    if not model or not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError(
            "No staging model configured. Provide EDITORIAL_PILOT_MODEL and "
            "GEMINI_API_KEY through Actions secrets; no AI call was made."
        )
    if not model.startswith("gemini/"):
        raise RuntimeError("Only a reviewed Gemini route is allowed for this staging canary.")

    route = ModelRoute(
        name="mukuru-staging-gemini",
        model=model,
        supports_json_mode=True,
        max_call_cost_usd=Decimal("0.06"),
        timeout_seconds=60,
        max_retries=0,
    )
    gateway = ModelGateway(
        LiteLLMClient(),
        model_policy=ModelPolicy(routes={
            ModelTask.RESEARCH_VERIFICATION: route,
            ModelTask.CONTENT_DRAFTING: route,
        }),
        budget_policy=BudgetPolicy(
            per_run_usd=MAX_COST_USD,
            default_per_agent_usd=Decimal("0.35"),
        ),
        budget_ledger=BudgetLedger(sessions),
    )
    research = ResearchVerificationAgent(sessions).verify(
        RUN_ID,
        adapter=ModelResearchAdapter(gateway),
        budget=ResearchBudget(
            max_sources=3,
            max_claims=6,
            max_evidence_items=12,
            max_adapter_calls=4,
        ),
        policy=VerificationPolicy(stale_after_hours=24 * 365),
        additional_source_item_ids=list(snapshot.additional_source_item_ids),
    )
    print(json.dumps({
        "research_status": research.status.value,
        "research_brief_id": str(research.research_brief_id),
        "verified_claims": len(research.claim_ids),
        "evidence_items": len(research.evidence_ids),
        "unsupported_claims": len(research.unsupported_claim_ids),
    }))
    if research.workflow_status != WorkflowStatus.VERIFIED.value:
        raise RuntimeError("Research did not reach VERIFIED; drafting stopped safely.")
    with sessions() as session:
        run = session.get(WorkflowRun, RUN_ID)
        assert run is not None
        pack = get_builtin_vertical_pack(run.vertical_key, run.vertical_version)
    article = ContentAgent(sessions).generate(
        RUN_ID, adapter=ModelContentAdapter(gateway),
        vertical_pack=pack, locale="fr", content_format="article",
    )
    print(json.dumps({
        "status": article.workflow_status,
        "draft_id": str(article.draft_id),
        "draft_version": article.version,
        "unsupported_factual_claims": article.unsupported_factual_claims,
        "citations": article.citation_count,
        "publication_allowed": False,
    }))


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled Mukuru editorial staging pilot")
    parser.add_argument("command", choices=["inspect", "enrich", "draft"])
    args = parser.parse_args()
    settings = Settings()
    if (
        settings.environment != "staging"
        or "editorial_os_staging" not in settings.database_url
    ):
        raise SystemExit("Fail closed: a dedicated editorial_os_staging database is required.")
    sessions = get_session_factory(settings)
    if args.command == "inspect":
        print(json.dumps(report(preflight(sessions)), indent=2, ensure_ascii=False))
        return 0
    if args.command == "enrich":
        enrich(sessions)
        print(json.dumps(report(preflight(sessions)), indent=2, ensure_ascii=False))
        return 0
    draft(sessions, preflight(sessions))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as error:
        # Avoid leaking credentials or request content in CI logs.
        print(
            f"Pilot stopped safely: {type(error).__name__}: {str(error)[:240]}",
            file=sys.stderr,
        )
        sys.exit(2)
