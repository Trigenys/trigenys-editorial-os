# Research & Verification

Issue #9 makes factual support a first-class artifact between Gate A and drafting.

## Boundary

The Research & Verification Agent consumes:
- the exact Gate-A-approved `TopicCandidate` version;
- normalized `SourceItem` records;
- Source Registry trust/evidence tiers;
- a bounded research budget;
- a versioned verification policy;
- a provider-agnostic `ResearchAdapter`.

It produces:
- canonical claims;
- extracted evidence;
- claim↔evidence links with stance;
- contradiction/stale/unsupported flags;
- confidence classes with machine-readable reasons;
- a versioned `ResearchBrief`.

It never treats model output itself as evidence.

## Primary-source-first plan

Sources are ordered deterministically:
1. E3/E4 sources as `PRIMARY`;
2. E2/E1 sources as `SECONDARY`;
3. higher tier before lower tier;
4. fresher material before older material.

The persisted research brief records the full ordered source plan and which entries were actually examined.

## Evidence extraction

A research adapter may use the existing ModelGateway, but it may only return:
- claim key;
- stance: `SUPPORTS | REFUTES | CONTEXT | NO_EVIDENCE`;
- a verbatim excerpt;
- a bounded reason code.

Editorial OS independently validates that every usable excerpt exists in the normalized source text. A non-verbatim or invented excerpt is rejected and cannot enter the evidence ledger.

Evidence tier and primary/secondary role come from Source Registry metadata, not from the model.

## Claim/evidence ledger

Each `Claim` has:
- stable `claim_key`;
- materiality;
- risk class;
- support status;
- confidence class;
- confidence reason codes;
- stale/contested flags.

Each claim↔evidence link stores the evidence stance and extraction reason code.

## Deterministic confidence

Confidence is evidence-derived:

- no supporting evidence → `C0 / UNSUPPORTED`;
- weak-only, stale-only, or credible contradiction → `C1`;
- one credible E2 source → `C2`;
- clear E3 primary or multiple independent E2 sources → `C3`;
- E4 or primary + independent credible corroboration → `C4`.

A material contradiction is never averaged away. It remains `CONTESTED` and routes to review.

Overall research confidence is the minimum confidence across material claims, not an average.

## Workflow routing

Automatic `VERIFICATION_COMPLETED` is allowed only when:
- every material claim has support;
- no review trigger applies;
- the deterministic confidence policy is satisfied.

Otherwise the workflow is moved to `BLOCKED` with the `ResearchBrief` as the review artifact.

Review triggers include:
- R2 sensitive risk;
- R3 restricted risk;
- C0/C1 material confidence;
- credible contradiction;
- policy-specific sensitive confidence shortfall.

R3 cannot be human-overridden into verified.

A human may resolve a `REVIEW_REQUIRED` brief only when material claims are not unsupported. The resolution is audited, resumes the blocked workflow, then completes verification. Unsupported material claims require new evidence.

## Bounded research

`ResearchBudget` limits:
- sources examined;
- claims;
- persisted evidence items;
- adapter/model calls.

Early stopping is allowed only after all material claims meet the configured confidence threshold and independent-source requirement.

Every brief records actual budget usage and any budget stop reason.

## Idempotency

A research input fingerprint includes:
- approved topic candidate/version;
- source item IDs;
- adapter identity;
- policy;
- research budget;
- explicit claims when supplied.

Repeating the same research request returns the existing brief and does not invoke the adapter or create duplicate claims/evidence.
