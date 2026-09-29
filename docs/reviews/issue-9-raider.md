# Issue #9 RAIDER review

## Reusable

Research planning, evidence extraction, confidence calculation, contradiction handling and budget limits are independent of one editorial vertical.

## Agnostic

The core depends on `ResearchAdapter`, not a vendor SDK. `ModelResearchAdapter` is one adapter over the existing provider-independent ModelGateway.

Evidence tier and source role are domain metadata, not provider output.

## Idempotent

The `ResearchBrief` owns a stable input fingerprint. Repeating the same request reuses the persisted brief and stable workflow action keys instead of paying for research/model calls again.

## Durable / non-regressive

The migration backfills legacy claims with stable legacy keys and safe `UNKNOWN` support status. Existing evidence receives explicit secondary/legacy defaults.

The historical workflow fixture was updated in the same change because Issue #7 established the rule: **schema evolution requires a constructor/fixture compatibility sweep before CI**.

## Engineering-grade

The system mechanically enforces:
- primary-source-first ordering;
- verbatim evidence excerpts;
- bounded research calls;
- persisted stance per claim/evidence link;
- deterministic confidence;
- contradiction surfacing;
- unsupported-claim blocking;
- sensitive/low-confidence human review.

The model cannot assign evidence tier or final confidence.

## Retroactive

Existing claims/evidence survive migration without being falsely reclassified as newly verified. Legacy claim support is `UNKNOWN` until processed by the new verification flow.

## Failure Memory / continuous learning

Two prior lessons are applied proactively:

1. New non-null persistence fields are swept across old factories before CI.
2. Retry paths are designed before the first CI run: research persistence and workflow handoff use stable fingerprints/action keys so a crash between those steps is recoverable.

A third rule is added here:

> **Never accept a model-generated evidence excerpt unless it can be mechanically located in the source material.**
