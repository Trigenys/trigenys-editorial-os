# Product contract

## Purpose

Trigenys Editorial OS is a reusable editorial operating system for a small AI-assisted newsroom. Its job is to move a source signal through research, drafting, quality control, approval, publication, distribution and performance feedback while keeping provenance, human authority and remote side effects auditable.

The core is **vertical-agnostic**. Trigenys Insight, GL media, anime, gaming, cyber watch or startup coverage are consumers expressed through versioned configuration and policy packs.

## MVP product promise

Given an approved source set and a vertical pack, one operator can supervise a complete editorial run from detected signal to published/distributed content from one control surface, with:
- evidence traceability for material factual claims;
- deterministic workflow state;
- three explicit human gates;
- retry-safe remote writes;
- model/provider replaceability;
- run-level cost, latency and failure visibility.

## Non-goals

The MVP does not promise:
- fully autonomous publication;
- support for every CMS/social network/model provider;
- unrestricted web crawling;
- model-generated factual claims without evidence;
- public profiles or reader identity features;
- one giant conversational agent that owns workflow state.

## Eleven business functions mapped to seven agents

The product contains eleven editorial responsibilities but only seven software agents.

1. Scout → **Scout Agent**
2. Topic analysis → **Editorial Intelligence Agent**
3. Editorial strategy/angle → **Editorial Intelligence Agent**
4. Source verification → **Research & Verification Agent**
5. Writing → **Content Agent**
6. Visual direction → **Creative Agent**
7. Editing/QA → **Editorial QA Agent**
8. Publishing → **Publishing & Growth Agent**
9. Distribution → **Publishing & Growth Agent**
10. Growth/performance analysis → **Publishing & Growth Agent**
11. Editor-in-Chief supervision → **deterministic policy + orchestrator**, not a conversational agent

## Agent contracts

### 1. Scout Agent

**Input**
- enabled Source Registry entries;
- fetch policy;
- last successful cursor/checkpoint;
- vertical eligibility rules.

**Output**
- normalized source items/signals;
- canonical URL/identity;
- source provenance;
- extraction/fetch status;
- content fingerprint.

**Must not**
- choose an editorial angle;
- mark a claim true;
- draft or publish content;
- mutate workflow state directly.

### 2. Editorial Intelligence Agent

**Input**
- normalized signals;
- recent topic history;
- vertical pack;
- editorial priorities.

**Output**
- topic candidate;
- duplicate/cluster identity;
- novelty and relevance reasoning;
- proposed angle;
- proposed format/urgency;
- decision: `IGNORE | WATCH | PROPOSE`.

**Must not**
- present unverified source claims as facts;
- publish;
- bypass Gate A;
- perform irreversible remote writes.

### 3. Research & Verification Agent

**Input**
- Gate-A-approved topic candidate and angle;
- source hierarchy;
- research budget;
- risk class.

**Output**
- evidence set;
- claim ledger;
- contradictions;
- freshness data;
- confidence class per claim/topic;
- unsupported/contested flags;
- research brief.

**Must not**
- silently discard contradictory evidence;
- convert model opinion into evidence;
- publish or alter a gate decision.

### 4. Content Agent

**Input**
- verified research brief;
- claim ledger;
- vertical pack;
- requested locale/format.

**Output**
- versioned draft;
- headline/deck/body;
- SEO metadata;
- internal-link suggestions;
- explicit references to supported claims.

**Must not**
- introduce a new material factual claim without marking it unsupported;
- fetch arbitrary sources as an undocumented side channel;
- publish.

### 5. Creative Agent

**Input**
- approved/eligible draft context;
- visual brief;
- brand/vertical rules;
- asset policy.

**Output**
- asset manifest;
- generated/selected asset candidates;
- alt text;
- caption;
- filename;
- provenance/rights metadata.

**Must not**
- conceal whether an asset is generated or externally sourced;
- imply a real event/person/image is authentic without provenance;
- publish independently.

### 6. Editorial QA Agent

**Input**
- draft;
- claim ledger/evidence;
- asset manifest;
- vertical style rules;
- risk/confidence policy.

**Output**
- structured findings;
- `PASS | REVISE | BLOCK`;
- unsupported-claim list;
- contradiction/freshness/style findings;
- Gate-B readiness.

**Must not**
- waive mandatory risk policy;
- repair evidence by inventing support;
- auto-approve its own blocked finding.

### 7. Publishing & Growth Agent

**Input**
- approved content package;
- Gate-C authorization;
- CMS/channel configuration;
- distribution policy;
- performance events.

**Output**
- CMS publication/draft reconciliation;
- channel-specific distribution jobs;
- publication/distribution receipts;
- performance snapshot;
- structured feedback signal for future topic planning.

**Must not**
- publish without Gate C in MVP;
- double-post on retry;
- modify canonical editorial facts from engagement data;
- treat analytics providers as the system of record.

## Editor-in-Chief / orchestrator contract

The Editor-in-Chief role is implemented by deterministic policy and the workflow engine.

It owns:
- legal state transitions;
- gate requirements;
- risk routing;
- idempotency ownership;
- retry policy;
- budget enforcement;
- escalation/block rules;
- audit correlation.

It does **not** write articles, invent evidence or make subjective editorial prose decisions.

Agents propose structured outputs. The orchestrator decides whether those outputs are valid inputs to the next state.

## Human gates

### Gate A — Topic approval

Occurs after `PROPOSE`, before expensive research/writing.

Operator can:
- approve;
- edit angle/format/priority;
- move to WATCH;
- reject.

Approval records actor, time, input version and approved angle.

### Gate B — Editorial approval

Occurs after QA has produced `PASS` or an explicitly reviewable exception.

Operator sees:
- final draft version;
- evidence/claim coverage;
- QA findings;
- exact asset versions.

Operator can approve, request revision or reject.

### Gate C — Publish approval

Occurs after the final package and publication target/schedule are known.

Operator confirms:
- destination;
- locale/version;
- schedule;
- distribution scope.

MVP never publishes without Gate C.

## Vertical pack contract

A vertical pack may configure:
- identity/name/version;
- audience;
- locales;
- voice/style;
- supported content formats;
- source hierarchy and allow/deny lists;
- risk overrides that only make policy stricter;
- prohibited patterns;
- SEO conventions;
- visual rules;
- CMS/channel mappings;
- performance goals.

A vertical pack must not:
- replace core workflow states;
- disable audit/provenance;
- weaken mandatory platform safety/risk policy;
- import provider SDK objects into domain contracts;
- require a fork of the core.

## Product invariants

These invariants are requirements for later automated tests.

**INV-001 — Evidence traceability**  
Every material factual claim that reaches `QA_PASSED` has at least one evidence reference or is explicitly marked as opinion/analysis.

**INV-002 — Human authority**  
In MVP, `PUBLISH_APPROVED` cannot be reached without an explicit Gate-C decision from an authorized operator.

**INV-003 — No agent-owned workflow truth**  
Agent output alone never mutates canonical workflow state.

**INV-004 — Retry safety**  
Repeating the same owned remote side effect with the same idempotency key does not create a duplicate publication, asset or distribution job.

**INV-005 — Risk cannot be averaged away**  
High-risk classification cannot be overridden solely by a high model confidence value.

**INV-006 — Provider independence**  
Domain objects do not contain vendor SDK objects or require one specific LLM/CMS/analytics provider.

**INV-007 — Versioned approvals**  
A gate approval applies to a specific version of its reviewed artifact. Material revision invalidates the relevant downstream approval.

**INV-008 — Provenance preservation**  
Research, drafting and publication retain enough linkage to reconstruct which evidence supported the published factual claims.

**INV-009 — Bounded execution**  
Every agent run has explicit timeout/retry/budget limits.

**INV-010 — Vertical neutrality**  
The core can onboard a materially different second vertical through configuration/adapters without branching on vertical name.

## MVP exit evidence

The product contract is demonstrated when a real pilot completes:

`signal → topic proposal → Gate A → research/evidence → draft → assets → QA → Gate B → publish package → Gate C → CMS → distribution preview/event → measurement`

and the run can be reconstructed from the audit record without reading model chain-of-thought or provider dashboards.
