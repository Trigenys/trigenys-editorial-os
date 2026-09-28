from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from editorial_os_api.db import get_engine
from editorial_os_api.persistence.models import (
    AuditEvent,
    GateDecision,
    Publication,
    brief_claim_links,
    claim_evidence_links,
    draft_claim_links,
)
from tests.factories import create_complete_workflow

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _upgrade_schema() -> None:
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def test_complete_workflow_fixture_persists_full_provenance() -> None:
    _upgrade_schema()
    suffix = uuid4().hex
    engine = get_engine()

    with Session(engine) as session:
        fixture = create_complete_workflow(session, suffix=suffix)

        claim_evidence_count = session.scalar(
            select(func.count()).select_from(claim_evidence_links).where(
                claim_evidence_links.c.claim_id == fixture.claim.id
            )
        )
        brief_claim_count = session.scalar(
            select(func.count()).select_from(brief_claim_links).where(
                brief_claim_links.c.editorial_brief_id == fixture.brief.id
            )
        )
        draft_claim_count = session.scalar(
            select(func.count()).select_from(draft_claim_links).where(
                draft_claim_links.c.draft_id == fixture.draft.id
            )
        )

        assert claim_evidence_count == 1
        assert brief_claim_count == 1
        assert draft_claim_count == 1
        assert fixture.source.redact_raw_content is True
        assert fixture.source.retention_days == 30


@pytest.mark.parametrize(
    ("model", "field", "replacement"),
    [
        (GateDecision, "outcome", "REJECTED"),
        (AuditEvent, "event_type", "tampered"),
    ],
)
def test_append_only_ledger_rejects_updates(
    model: type[GateDecision] | type[AuditEvent],
    field: str,
    replacement: str,
) -> None:
    _upgrade_schema()
    suffix = uuid4().hex
    engine = get_engine()

    with Session(engine) as session:
        fixture = create_complete_workflow(session, suffix=suffix)
        entity = (
            fixture.editorial_gate
            if model is GateDecision
            else fixture.audit_event
        )

        with pytest.raises(DBAPIError):
            session.execute(
                update(model)
                .where(model.id == entity.id)
                .values({field: replacement})
            )
            session.commit()

        session.rollback()


def test_publication_idempotency_constraint_blocks_duplicate_owned_write() -> None:
    _upgrade_schema()
    suffix = uuid4().hex
    engine = get_engine()

    with Session(engine) as session:
        fixture = create_complete_workflow(session, suffix=suffix)

        duplicate = Publication(
            workflow_run_id=fixture.workflow.id,
            draft_id=fixture.draft.id,
            provider=fixture.publication.provider,
            target=fixture.publication.target,
            status="PUBLISHED",
            owner_key="different-owner-does-not-bypass-idempotency",
            idempotency_key=fixture.publication.idempotency_key,
            external_id="duplicate",
            external_url=None,
            scheduled_at=None,
            published_at=None,
            receipt={},
        )
        session.add(duplicate)

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()
