# Editorial domain model

Issue #3 defines the canonical persistence and contract boundary for the Editorial OS.

## Separation

```text
agents / API
    │
    ▼
domain contracts (Pydantic)
    │
    ▼
application / orchestration
    │
    ▼
persistence models (SQLAlchemy)
    │
    ▼
PostgreSQL
```

Provider SDK objects never cross into the domain contract.

## Canonical entities

- `Source` — configured source identity and retention policy.
- `SourceItem` — normalized fetched source item with deduplication fingerprint and redaction/retention state.
- `WorkflowRun` — one canonical editorial run and its current lifecycle classification.
- `TopicCandidate` — editorial proposal produced from one or more signals.
- `EvidenceItem` — evidence with provenance, freshness and retention metadata.
- `Claim` — factual/editorial statement classified by materiality, confidence and risk.
- `claim_evidence_links` — many-to-many support graph between claims and evidence.
- `EditorialBrief` — versioned approved/research-informed angle and instructions.
- `Draft` — versioned locale-specific article body.
- `Asset` — versioned image/video/document manifest with provenance.
- `GateDecision` — immutable human decision against a specific artifact version.
- `AuditEvent` — immutable event ledger for consequential state/actions.
- `Publication` — CMS-side effect ownership and receipt.
- `DistributionJob` — channel-side effect ownership and receipt.
- `PerformanceSnapshot` — timestamped performance metrics linked back to the run.

## Claim/evidence rule

A claim can have zero or more evidence links while research is in progress, but Issue #12 must prevent a material unsupported claim from reaching `QA_PASSED`.

The database stores the graph; policy determines whether the graph is sufficient.

## Version ownership

Mutable editorial artifacts are versioned rather than silently overwritten where approval history matters:

- editorial brief: `workflow_run_id + version`;
- draft: `workflow_run_id + locale + version`;
- asset: `workflow_run_id + kind + version`.

A `GateDecision` records `artifact_type + artifact_id + artifact_version`. Editing an artifact produces a new version and therefore cannot inherit approval accidentally.

## Append-only records

`gate_decisions` and `audit_events` are append-only.

PostgreSQL triggers reject `UPDATE` and `DELETE` on those tables. Corrections are represented by a new event/decision, preserving history.

## Remote side-effect ownership

Every managed publication/distribution mutation has:

- `owner_key` — identifies the resource as owned/reconcilable by Editorial OS;
- `idempotency_key` — identifies the logical desired side effect;
- provider/target or provider/channel;
- external receipt/ID.

Uniqueness constraints make accidental duplicate owned writes mechanically detectable.

## Sensitive source retention

`Source`, `SourceItem` and `EvidenceItem` contain retention/redaction fields:

- source-level `retention_days`;
- source-level `redact_raw_content`;
- item/evidence `retain_until`;
- item/evidence `redacted_at`.

Issue #7/#9 will implement policy behavior around these fields. The core schema does not assume raw third-party content should be stored forever.

## Audit rule

The audit ledger stores consequential facts, not model chain-of-thought.

Examples:
- gate approval/rejection;
- workflow transition;
- risk/confidence reclassification;
- remote publication attempt/result;
- budget stop;
- operator revision request.

Useful evidence/provenance is retained; hidden reasoning traces are not a product requirement.
