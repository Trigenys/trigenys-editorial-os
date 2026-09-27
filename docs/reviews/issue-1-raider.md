# RAIDER review — Issue #1 product contract

## Reusable

- The core contract models editorial capabilities, not Trigenys Insight behavior.
- Vertical-specific voice, sources, locales and channels live in versioned vertical packs.
- Eleven business functions are expressed through seven reusable agent responsibilities.

## Agnostic

- Provider SDK objects are forbidden from domain contracts.
- LLM, CMS, analytics, ingestion and distribution providers sit behind ports/adapters.
- Absolute monetary budgets and source lists are configuration, not core constants.

## Idempotent

- Retry safety is a product invariant.
- Remote writes require stable idempotency ownership.
- Duplicate owned publication/distribution side effects have an MVP target of zero.

## Durable / Non-regressive

- Decisions are versioned as ADRs.
- Approvals are tied to artifact versions.
- Later architecture changes supersede ADRs rather than rewriting history.

## Engineering-grade

- Risk and confidence are separate, explicit policies.
- Material factual claims require stored evidence.
- The Editor-in-Chief role is deterministic policy rather than an LLM persona.
- MVP success metrics are defined before implementation.
- Reuse-first ecosystem decisions are recorded in `docs/ecosystem-reconnaissance.md`.

## Retroactive

- Vertical packs configure behavior without forking the core.
- Provider boundaries preserve an exit path.
- The second-consumer release criterion explicitly tests portability rather than assuming it.

## Issue #1 Proof of Done mapping

- [x] Product invariants are documented and testable in later implementation issues.
- [x] Agent inputs/outputs and non-responsibilities are named and bounded.
- [x] Gate A/B/C semantics are explicit.
- [x] R0–R3 risk classes define when automatic progression/publication is forbidden.
- [x] Initial runtime/orchestration/persistence/provider-policy ADRs are committed.
- [x] Core contract contains no required vertical-specific behavior.
- [x] RAIDER review completed.
