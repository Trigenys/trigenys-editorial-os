# Risk and confidence policy

Risk and confidence are independent dimensions.

- **Risk** asks: *What is the harm/cost if this is wrong or exposed?*
- **Confidence** asks: *How well is this specific claim supported by evidence?*

A high-confidence claim can still be high-risk. Risk policy always wins over confidence.

## Evidence source tiers

Source tiers describe provenance, not truth by themselves.

### E0 — No usable evidence
Rumor, unattributed screenshot, unsourced model output or inaccessible claim.

### E1 — Community / weak secondary
Forum post, social commentary, aggregation with unclear origin, anonymous report.

Useful as a discovery signal, not enough by itself for material factual publication.

### E2 — Credible secondary
Established specialist publication, reputable press, named expert analysis, well-attributed database.

### E3 — Primary / authoritative
Official account, first-party statement, source document, direct interview, public record, platform announcement, original dataset where applicable.

### E4 — Primary + independent corroboration
Direct/authoritative evidence plus at least one materially independent credible corroboration, or multiple independent primary sources.

## Confidence classes

Confidence is derived from the evidence ledger and contradiction state. A model is not allowed to assign confidence merely from how plausible text sounds.

### C0 — Unsupported
No usable evidence for the material claim.

Action: block factual publication.

### C1 — Low
Only E1 evidence, stale evidence, unresolved identity/date ambiguity, or material contradiction.

Action: WATCH or human escalation; cannot auto-progress past QA.

### C2 — Moderate
At least one credible E2 source, or one E3 source with meaningful ambiguity that remains.

Action: publication requires human review; sensitive topics need stronger support.

### C3 — High
Clear E3 primary evidence with no material unresolved contradiction, or multiple independent E2 sources with strong agreement.

Action: eligible for normal editorial flow, still subject to risk gates.

### C4 — Confirmed
E4 support or direct authoritative evidence whose meaning is unambiguous for the claim being made.

Action: strongest evidence class; does not waive risk policy.

## Risk classes

### R0 — Routine

Examples:
- product release notes;
- public event schedules;
- entertainment release dates from official sources;
- technical documentation;
- non-sensitive business announcements.

MVP policy:
- Gate A: required;
- Gate B: required;
- Gate C: required.

Future policy may reduce gates after reliability evidence exists.

### R1 — Elevated

Examples:
- claims mainly sourced from secondary reporting;
- fast-moving breaking information;
- financial/business claims that could affect reputation or decisions;
- rumors being covered as rumors;
- content involving minors without sensitive personal detail.

Policy:
- human gates remain mandatory;
- C0/C1 cannot pass QA;
- at least C2 required for factual assertions;
- uncertainty must be explicit where material.

### R2 — Sensitive

Examples:
- allegations of misconduct/crime;
- health/medical claims about identifiable people;
- sexuality or identity claims not clearly self-disclosed/publicly established;
- death/injury;
- legal disputes;
- election/political claims;
- violence, harassment or safety incidents;
- private-person personal data;
- claims likely to materially damage reputation.

Policy:
- all three human gates mandatory;
- primary-source-first research required;
- C3 minimum for ordinary factual assertion unless reporting uncertainty itself is the story;
- unresolved contradiction blocks;
- no automated publication;
- QA must surface privacy/defamation/context concerns.

### R3 — Restricted / stop

Examples:
- doxxing or non-public sensitive personal information;
- unverifiable accusation presented as fact;
- content whose acquisition/use appears unlawful;
- content requiring a policy/legal exception that the system cannot determine safely;
- source/asset rights conflict with no usable permission basis.

Policy:
- workflow enters `BLOCKED`;
- no auto-drafting for publication when doing so would amplify the harm;
- no publication/distribution until an authorized human resolves the block or rejects the item;
- confidence score cannot override R3.

## Risk escalation rules

Risk is the maximum applicable class across:
- topic;
- claim;
- person/entity involved;
- source acquisition method;
- asset;
- publication/distribution context.

A downstream agent may increase risk but cannot reduce it below the last human-approved risk class without explicit reclassification evidence and audit history.

## Contradictions

A material contradiction means credible evidence supports incompatible versions of a claim.

Rules:
- contradiction is stored explicitly;
- confidence cannot be C4 while a material contradiction is unresolved;
- R2 + material contradiction blocks QA;
- editorial copy may accurately report the existence of a dispute if evidence supports that narrower claim.

## Freshness

Evidence has:
- observed/published time where known;
- fetched time;
- optional expiry/freshness policy.

A source can be authoritative but stale. Freshness affects confidence for claims that can change over time.

## Sensitive-content escalation

The orchestrator routes to mandatory human review when any of the following occurs:
- risk >= R2;
- confidence <= C1 for a proposed factual claim;
- material contradiction;
- source identity cannot be established;
- asset provenance/rights unresolved;
- draft introduces a material claim absent from the claim ledger;
- operator-defined vertical rule requests escalation.

## Required audit fields

At minimum:
- risk class and reason codes;
- confidence class and reason codes;
- evidence IDs used;
- contradictions;
- policy version;
- actor/model producing the assessment;
- timestamps;
- human override/reclassification record when applicable.
