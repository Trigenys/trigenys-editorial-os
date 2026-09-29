# Editorial Intelligence

Issue #8 turns normalized Scout signals into explainable topic proposals without treating source claims as verified facts.

## Boundary

The Editorial Intelligence Agent consumes:
- normalized `SourceItem` records;
- recent topic history for the same vertical;
- a versioned `VerticalIntelligencePolicy`;
- the existing model gateway when strategy enrichment is enabled.

It produces one versioned `TopicCandidate` for the selected signal cluster.

It does not:
- verify claims;
- draft article copy;
- publish;
- bypass Gate A;
- let a model decide `IGNORE | WATCH | PROPOSE`.

## Deterministic clustering

Signal text is normalized into token sets and grouped with configurable Jaccard similarity.

A cluster receives a deterministic `cluster_key` built from consensus tokens. Multiple reports of the same event therefore reconcile into one topic candidate while retaining every contributing `source_item_id`.

The workflow run + cluster key uniqueness constraint makes retries idempotent.

## Explainable scoring

Three bounded scores feed the deterministic decision:

- **novelty** — recent exact/similar topic history lowers the score;
- **relevance** — vertical priority/blocked terms are configuration, not code branches;
- **source diversity** — independent source IDs raise diversity.

The weighted composite is configured by the vertical pack.

Machine-readable reason codes include examples such as:
- `NOVEL_TOPIC`;
- `DUPLICATE_RECENT_TOPIC`;
- `SIMILAR_RECENT_TOPIC`;
- `VERTICAL_PRIORITY_MATCH`;
- `LOW_VERTICAL_RELEVANCE`;
- `CROSS_SOURCE_CLUSTER`;
- `STALE_SIGNAL`;
- `BLOCKED_VERTICAL_TERM`.

Stale or recently duplicated topics are capped at `WATCH`/ `IGNORE` even when another score is high.

## Model boundary

The model gateway may enrich:
- proposed angle;
- proposed format;
- urgency.

The model cannot alter:
- cluster membership;
- novelty/relevance/diversity scores;
- the deterministic `IGNORE | WATCH | PROPOSE` decision;
- Gate A requirements.

Invalid, unavailable or over-budget model strategy falls back to deterministic framing and records `MODEL_STRATEGY_FALLBACK`.

## Gate A

Only `PROPOSE` transitions the workflow from `INGESTED` to `CANDIDATE`.

MVP Gate A then remains mandatory. Pre-research candidates are intentionally stored at confidence `C1`; they cannot progress to verification before topic approval.

An operator may edit the candidate angle while Gate A is pending. The edit:
- increments `TopicCandidate.version`;
- writes an audit event;
- invalidates the stale expected version for the Editorial Intelligence Gate-A handoff.

Gate decisions continue to store the exact artifact version they reviewed.

## Vertical-pack contract

`VerticalIntelligencePolicy` configures:
- vertical key/version;
- eligible locales;
- priority terms;
- blocked terms;
- supported/default formats;
- cluster similarity threshold;
- scoring weights;
- decision thresholds;
- freshness and novelty windows;
- model strategy enablement.

No vertical name is hardcoded into the scoring engine.
