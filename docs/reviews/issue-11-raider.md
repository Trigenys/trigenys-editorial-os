# Issue #11 RAIDER review

## Reusable

The Creative Agent core consumes generic visual briefs and an `AssetProvider` protocol. Image generation, stock libraries, operator-provided media and later video renderers can use the same boundary.

## Agnostic

Provider SDK objects never enter the domain model. The manifest stores provider-neutral provenance, rights, generation metadata and variants.

No code branches on a vertical name; visual policy comes from the versioned vertical-pack snapshot.

## Idempotent

The manifest has a stable input fingerprint and database uniqueness constraint. The exact same request is returned before another planner/provider call.

Every remote asset slot receives its own stable provider idempotency key.

## Durable / non-regressive

The existing `workflow_run_id + kind + asset version` identity remains intact. New manifests add a second identity layer without invalidating legacy assets.

New Asset fields have safe ORM/migration defaults for old constructors.

Downgrade remains representable because the legacy uniqueness constraint was preserved instead of being dropped and reconstructed after multi-asset data exists.

## Engineering-grade

The system mechanically enforces:
- text-only articles without placeholder images;
- unique visual slots;
- pack-defined asset count/kind/aspect-ratio rules;
- alt/caption requirements;
- external source provenance;
- license metadata for externally sourced assets claimed as rights-clear;
- generation metadata for generated assets;
- provenance for operator-provided assets;
- conservative rights aggregation;
- exact Gate-B asset version snapshots.

## Retroactive

Legacy assets remain valid with:
- generated legacy slot identity;
- `PROVIDED` origin;
- `legacy` provider;
- `REVIEW_REQUIRED` rights by default.

They are not silently reclassified as rights-clear.

## Failure Memory / continuous learning

Applied lessons:
1. schema evolution preserves old constructors and migration round trips;
2. provider calls own stable idempotency keys before the first remote write;
3. mutable editorial configuration is snapshotted with produced artifacts;
4. provenance and rights are explicit, separate fields;
5. test fixtures prove cross-test compatibility before CI.

New rule:

> **Never infer asset usage rights from how an asset was obtained; persist origin, provenance and rights status independently.**
