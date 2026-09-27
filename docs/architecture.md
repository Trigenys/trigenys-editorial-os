# Architecture

## Goal

Trigenys Editorial OS lets one operator supervise an AI-assisted editorial pipeline without turning the system into one opaque autonomous agent.

## Logical architecture

```text
Source adapters
RSSHub / websites / APIs / manual URLs
          │
          ▼
     Source Registry
          │
          ▼
       Scout Agent
          │
          ▼
 Editorial Intelligence
(topic clustering, dedupe, angle proposal)
          │
      [Gate A]
          │
          ▼
 Research & Verification
(evidence graph + claim ledger)
          │
          ▼
      Content Agent
          │
          ├────────────► Creative Agent
          │
          ▼
    Editorial QA Agent
          │
      [Gate B]
          │
          ▼
 Publishing & Growth Agent
      [Gate C]
          │
          ├── Payload / CMS
          ├── Postiz / social
          ├── n8n / integrations
          └── PostHog / performance
```

## Runtime boundaries

### Web console
React/TypeScript/Vite. It displays queues, evidence, gates, runs, costs and performance. It never owns workflow truth.

### API and orchestration
FastAPI exposes operator and integration APIs. LangGraph is the initial orchestration candidate because the product needs stateful, resumable graphs and human-in-the-loop checkpoints.

### Domain core
Provider-independent Python modules define:
- source;
- signal;
- topic candidate;
- evidence item;
- claim;
- editorial brief;
- draft;
- asset;
- approval gate;
- publication;
- distribution job;
- performance snapshot;
- workflow run.

### Persistence
PostgreSQL stores product state, audit data, idempotency keys and workflow metadata. Raw external content should be retained only when useful and legally/operationally justified.

### Provider adapters
All external systems sit behind explicit interfaces. Initial candidates:
- RSSHub / Crawl4AI for source acquisition;
- LiteLLM for model routing;
- Langfuse for LLM tracing/evaluation;
- Payload for CMS;
- Postiz for social distribution;
- n8n for peripheral integration workflows;
- PostHog for product/content analytics;
- Remotion for templated video after the core text/image path is stable.

## Product policy references

The implementation contract is split across:
- [Product contract](product-contract.md) — agent responsibilities, gates, invariants and vertical-pack rules;
- [Risk and confidence policy](risk-and-confidence.md) — evidence tiers, confidence classes and R0–R3 escalation;
- [MVP metrics](mvp-metrics.md) — measurable exit criteria;
- [ADRs](adr/README.md) — accepted architecture choices and exit strategies.

## Seven agents

1. **Scout** — detects signals and normalizes source items.
2. **Editorial Intelligence** — clusters/deduplicates signals, estimates relevance and proposes angles.
3. **Research & Verification** — finds primary evidence, builds claims and confidence.
4. **Content** — creates the editorial draft and metadata from verified evidence.
5. **Creative** — creates/selects assets from an approved visual brief.
6. **Editorial QA** — checks factual support, style, policy and consistency.
7. **Publishing & Growth** — publishes, distributes and feeds performance back into planning.

The **Editor-in-Chief role is policy**, implemented by the orchestrator and gate engine, not an eighth conversational agent.

## Three human gates

- **Gate A — Topic:** approve/reject/edit angle before expensive research and writing.
- **Gate B — Editorial:** approve article + visual package after QA.
- **Gate C — Publish:** final release authorization and schedule/channel confirmation.

Gates are configurable by vertical and risk class. The MVP keeps all three enabled.

## Workflow states

```text
INGESTED
→ CANDIDATE
→ TOPIC_APPROVED
→ VERIFIED
→ DRAFTED
→ ASSETS_READY
→ QA_PASSED
→ EDITORIAL_APPROVED
→ READY_TO_PUBLISH
→ PUBLISH_APPROVED
→ PUBLISHED
→ DISTRIBUTED
→ MEASURED
```

Terminal/exception states include `REJECTED`, `BLOCKED`, `FAILED_RETRYABLE` and `FAILED_TERMINAL`.

## Idempotency

Every side effect receives a stable idempotency key derived from the workflow run and action identity. Before a remote write the adapter inspects owned state; retries reconcile rather than duplicate.

## Security

- no provider secret in the repository;
- least-privilege credentials;
- provenance on every material claim;
- audit record on gate decisions and publication mutations;
- vertical-specific safety/privacy rules remain configurable;
- public repo contains interfaces and examples only, never production credentials or private source lists.

## Accepted initial architecture decisions

- React/Vite console + Python/FastAPI service runtime — ADR-0001.
- LangGraph as the first workflow-engine implementation behind an internal boundary — ADR-0002.
- PostgreSQL as canonical product/domain state — ADR-0003.
- Ports/adapters around every external provider — ADR-0004.
- Editor-in-Chief as deterministic policy/orchestrator rather than an eighth agent — ADR-0005.

## Architecture decisions still to validate

- storage strategy for large fetched documents/assets;
- whether queues are necessary in MVP or Postgres-backed orchestration is sufficient;
- provider contract for image generation;
- deployment target.

Unresolved decisions require ADRs backed by integration evidence rather than preference alone.
