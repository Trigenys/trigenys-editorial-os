# Reuse-first ecosystem reconnaissance

RAIDER requires ecosystem reconnaissance before building non-trivial capabilities from scratch.

## Current decisions

### RSSHub — Adapt
Use as a source-feed adapter where routes are stable and permitted. Do not make the domain depend on RSSHub-specific payloads.

### Crawl4AI — Adopt/Adapt
Primary candidate for turning supported web pages into LLM-friendly structured content. Wrap behind a fetch/extract interface and keep a simple HTTP fallback.

### GPT Researcher — Learn/Adapt
Study research decomposition, source collection and citation patterns. Do not embed the entire product as the core workflow unless integration tests prove the coupling worthwhile.

### STORM / Co-STORM — Learn
Use its research-to-outline patterns for long-form editorial work. It is not the newsroom orchestrator.

### LangGraph — Adapt
Primary candidate for durable stateful orchestration and human checkpoints. Domain workflow states and policies remain ours.

### LiteLLM — Adapt
Candidate model gateway for provider abstraction, routing and cost controls.

### Langfuse — Adopt/Adapt
LLM tracing/evaluation boundary. Product audit history still lives in our own domain store.

### Payload — Adapt
Initial CMS adapter and first publishing target. The engine must support another CMS later without data-model surgery.

### n8n — Adapt
Peripheral workflow/integration layer. It must not own canonical editorial state or core decision policy.

### Postiz — Adapt
Candidate distribution adapter to avoid reimplementing every social network integration.

### PostHog — Adopt/Adapt
Performance and product analytics. Editorial truth and audit evidence stay in PostgreSQL.

### Remotion — Adapt later
Rich-media renderer after the text/image editorial path is reliable.

## Build ourselves

We should own the parts that are the actual product:
- editorial domain model;
- evidence/claim ledger;
- workflow and gate policy;
- vertical-pack contract;
- risk/confidence policy;
- operator experience;
- idempotency ownership model;
- provider-agnostic audit trail;
- performance feedback policy.

## Evaluation checklist

Before an external project becomes a hard dependency, verify:
- maintenance activity;
- license and commercial implications;
- security posture;
- deployment model;
- API stability;
- data/privacy implications;
- cost;
- testability;
- exit strategy.
