# Editorial QA and confidence/risk policy

Issue #12 adds the fail-closed quality boundary between `ASSETS_READY` and Gate B.

## Authority split

Editorial QA deliberately separates deterministic policy from semantic model review.

Deterministic code owns claim-to-draft support, missing evidence, unsupported assertions, source freshness, contradiction state, confidence thresholds, risk escalation, asset rights, vertical-pack mechanical rules, and workflow transitions.

The optional `EditorialQAAdapter` may report semantic findings such as misleading headline/body relationships, material internal contradictions in prose, asset/text mismatch, and editorial quality defects.

Model output is input to policy. It cannot turn an unsupported claim into a supported one, clear restricted rights, lower risk, or bypass a human gate.

## Outcomes

Every review has one structured outcome:

- `PASS`: no ERROR/BLOCKER finding; workflow advances `ASSETS_READY → QA_PASSED`.
- `REVISE`: at least one ERROR and no BLOCKER; workflow returns `ASSETS_READY → DRAFTED`.
- `BLOCK`: at least one BLOCKER; workflow enters `BLOCKED`.

Warnings remain visible without changing PASS. This is how high-risk human approval and unresolved-but-reviewable asset rights stay explicit for Gate B.

## Evidence rules

A material claim cannot PASS when it has no supporting evidence edge.

Material claims also fail QA when support is `UNSUPPORTED` or `UNKNOWN`, supporting evidence is stale, the claim is contested, or confidence is below the configured QA minimum.

Unsupported factual assertions already recorded by the Content Agent are BLOCKER findings. QA verifies the persisted claim/evidence graph instead of trusting prose or a second model opinion.

## Risk policy

`EditorialQAPolicy` is versioned and persisted with the review. The default requires at least C2 for routine/elevated material claims and C3 for R2/R3 claims, marks R2 and R3 as human-approval-required, blocks R3, requires semantic consistency checks, blocks unsupported material claims and restricted asset rights, and escalates unresolved R2/R3 contradictions.

High risk is never neutralized by high model confidence.

## Vertical-pack checks

QA reuses the exact `VerticalPack` snapshot stored with the draft. Mechanical checks cover prohibited phrases, headline/deck length, minimum section count, required visual presence, alt text, and captions.

## Provenance and retry safety

A QA review fingerprints exact draft content/version, asset manifest/version, claim state, supporting evidence state, assets, vertical-pack snapshot, QA policy, and semantic adapter identity.

The persisted `QASubjectSnapshot` records the exact draft, manifest, asset, claim and evidence IDs under review. Repeating the same QA request reuses the prior `EditorialQAReview` and does not invoke the semantic adapter again.

## Gate B

A PASS means the package is technically ready to be presented at Gate B. It is not itself editorial approval.

Gate B remains a human decision in the MVP. R2/R3 content and asset-rights-review cases are additionally marked `human_approval_required` so the reason remains visible and auditable.
