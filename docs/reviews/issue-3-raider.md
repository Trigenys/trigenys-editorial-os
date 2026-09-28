# RAIDER review — Issue #3 domain model and audit ledger

## Reusable

- Domain contracts model editorial concepts rather than any one publication brand.
- Persistence is split into source, workflow, evidence, content, governance and delivery modules.
- The same claim/evidence/approval model can serve multiple vertical packs.

## Agnostic

- Pydantic domain contracts reject provider-specific extra state.
- External provider identifiers/receipts are stored only at adapter-facing persistence boundaries.
- No CMS, LLM, analytics or social SDK object exists in the domain layer.

## Idempotent

- Workflow runs have stable idempotency keys.
- Publications enforce provider + target + idempotency key uniqueness.
- Distribution jobs enforce provider + channel + idempotency key uniqueness.
- Source items deduplicate by source/external ID and source/content hash.

## Durable / Non-regressive

- The schema is introduced as Alembic revision `20260928_0002`.
- Existing runtime migration `0001` remains intact.
- Migration tests exercise downgrade/upgrade of the full chain.
- Approval history is version-bound rather than overwritten.

## Engineering-grade

- Claims link to evidence mechanically.
- Briefs and drafts explicitly link to the claims they consume.
- Gate decisions and audit events are append-only at the PostgreSQL layer through mutation-rejection triggers.
- Retention/redaction fields are first-class for source/evidence content.
- A complete workflow fixture exercises the schema without external APIs.
- Audit events store consequential facts, not model chain-of-thought.

## Reuse-first

The capability is mostly product-specific domain value, so the decision is **Build** on top of mature adopted primitives:
- SQLAlchemy 2.0 ORM and metadata
- PostgreSQL UUID/JSONB
- Alembic migrations
- Pydantic v2 contracts

No external newsroom schema was adopted because the differentiating product requirement is the evidence + gates + idempotency ownership model.

## Retroactive

- The schema is additive to the runtime introduced by Issue #2.
- The migration chain preserves the previous empty bootstrap revision.
- External IDs are optional, enabling ingestion of existing/brownfield records later.
- Provider-specific data remains adapter metadata, so integrations can be replaced without resetting canonical editorial records.

## Issue #3 Proof of Done mapping

- [x] Domain objects contain no provider SDK objects.
- [x] Material claims can link to one or more evidence items.
- [x] Brief/draft provenance can identify exactly which claims fed each version.
- [x] Gate decisions are immutable and auditable.
- [x] Audit events are append-only.
- [x] Remote side effects persist ownership and idempotency keys.
- [x] Schema migrations are covered by the existing migration round-trip plus new domain tests.
- [x] Source/evidence retention and redaction fields exist.
- [x] A complete workflow fixture can be created without external APIs.
