# Issue #10 RAIDER review

## Reusable

The Content Agent depends on a generic `VerticalPack` and `ContentAdapter`. The same generation/revision core serves the generic demo and Trigenys Insight pilot.

## Agnostic

No core branch checks whether the vertical is Trigenys Insight or another publication. Locale, formats, voice, SEO and source behavior all come from configuration.

The model provider remains behind the existing ModelGateway.

## Idempotent

Generation fingerprints the research brief, pack snapshot, locale, format and adapter. Revision adds the parent draft and operator feedback.

Repeated identical requests reuse persisted drafts instead of issuing duplicate model calls.

## Durable / non-regressive

Draft provenance persists:
- research brief;
- editorial brief;
- pack key/version/snapshot;
- source citations;
- claim links;
- revision ancestry.

The legacy `Draft(...)` constructor keeps a safe ORM fingerprint default so schema evolution does not break historical fixtures.

## Engineering-grade

The model writes prose, but Editorial OS owns:
- which claims are authorized;
- whether a claim key exists;
- citation construction;
- unsupported-claim classification;
- style validation;
- workflow transition;
- version ownership.

Unknown factual assertions cannot be silently upgraded to supported.

## Retroactive

Migration 0008 backfills historical drafts with legacy pack identity and unique legacy fingerprints. Existing drafts remain readable without pretending they were produced by the new Content Agent.

## Failure Memory / continuous learning

Applied lessons:
1. non-null schema additions include constructor/fixture compatibility in the same change;
2. canonical provenance is generated from persisted ledger state rather than trusted from model output;
3. test fixtures are isolated from unrelated registries/verticals;
4. style/lint constraints are checked before the first CI run.

New rule:

> **Editorial configuration that can change output must be persisted as a versioned snapshot with the artifact it produced.**
