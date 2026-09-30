# Issue #12 RAIDER review

## Reusable

Editorial QA depends on generic draft, claim/evidence, asset-manifest and vertical-pack contracts. Semantic review is behind `EditorialQAAdapter`. No QA rule depends on Trigenys Insight by name.

## Agnostic

The deterministic layer owns evidence, risk, confidence, rights and state transitions. The model provider remains behind the existing `ModelGateway` and `EDITORIAL_QA` task. The semantic adapter cannot override policy.

## Idempotent

QA inputs are fingerprinted from exact draft, manifest, claims, evidence, assets, vertical pack, policy and adapter identity. An identical retry reuses the persisted review before any second semantic-model call.

## Durable / non-regressive

`EditorialQAReview` persists PASS / REVISE / BLOCK, structured findings, risk and confidence, human-approval requirement, Gate-B readiness, policy version/snapshot, and the exact subject snapshot.

Workflow revision is a first-class transition from `ASSETS_READY` back to `DRAFTED`, rather than an out-of-band mutation.

## Engineering-grade

The QA model does not decide factual truth. Mechanical policy checks the canonical persisted ledger and produces machine-readable findings with code, severity, category, claim/evidence/asset references, policy rule and metadata.

A material claim without evidence cannot PASS.

## Retroactive

Migration 0010 is additive. Existing drafts and manifests remain readable. Historical runs are not rewritten to pretend they passed the new QA stage.

## Failure Memory / continuous learning

Applied lessons:
1. policy remains deterministic and separate from model critique;
2. approvals refer to exact artifact versions;
3. retry keys include every versioned input that can change the decision;
4. provider-specific objects do not cross the QA boundary;
5. revisions return through the canonical workflow state machine.

New rule:

> **A probabilistic reviewer may discover a defect, but only deterministic policy may authorize a workflow transition.**
