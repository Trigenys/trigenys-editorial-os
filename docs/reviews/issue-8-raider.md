# Issue #8 RAIDER review

## Reusable

Clustering, scoring, decision thresholds and model strategy are reusable across any vertical through `VerticalIntelligencePolicy`.

## Agnostic

Core logic contains no Trigenys Insight, gaming, anime, cyber-watch or other vertical-name branches. The model gateway remains provider-independent.

## Idempotent

A topic candidate is uniquely owned by `workflow_run_id + cluster_key`. A `PROPOSE` transition uses a stable workflow action key derived from candidate ID/version.

## Durable / non-regressive

Topic scoring is persisted with the candidate. Operator angle edits are versioned and audited. Existing workflow/domain fixtures were updated in the same schema change rather than left for CI to discover later.

## Engineering-grade

The deterministic layer owns:
- clustering;
- novelty/relevance/source-diversity scoring;
- stale/duplicate caps;
- `IGNORE | WATCH | PROPOSE`;
- Gate A handoff.

The model can only enrich angle/format/urgency and its output is schema-validated and budgeted.

## Retroactive

The migration backfills existing topic candidates with legacy cluster keys and safe defaults so historical rows survive the schema extension.

## Failure Memory / continuous learning

Issue #7 exposed two process failures that are explicitly avoided here:

1. **Schema evolution requires a constructor/fixture compatibility sweep before CI.**
2. **Lint/type fixes should follow tool diagnostics exactly rather than guess formatting/order.**

Issue #8 therefore updates the historical workflow fixture alongside the schema and keeps deterministic tests for new and old paths.
