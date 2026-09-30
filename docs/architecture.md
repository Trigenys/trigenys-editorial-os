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
FastAPI exposes operator and integration APIs. LangGraph 1.2.x is the first orchestration implementation behind the internal `WorkflowEngine` boundary. PostgreSQL-backed checkpoints provide pause/resume mechanics, while canonical status, gate decisions, action idempotency and audit remain Editorial OS domain state.

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

### Source acquisition
The Source Registry owns approved source configuration, vertical eligibility, trust/evidence defaults, fetch policy, cursor and health. The deterministic Scout Agent persists each raw fetch separately from its normalized canonical `SourceItem`.

RSS/Atom is the baseline feed path. RSSHub is a route adapter over the same feed boundary. Manual URLs use a replaceable `PageExtractor`, with lightweight HTTP extraction by default and Crawl4AI as an optional heavier adapter.

Canonical URL normalization plus source-scoped identity/content fingerprints make repeated ingestion idempotent without erasing fetch provenance.

### Editorial intelligence
The Editorial Intelligence Agent clusters normalized signals across sources, scores novelty/relevance/source diversity, and deterministically chooses `IGNORE | WATCH | PROPOSE` from a versioned vertical policy.

Only `PROPOSE` enters `CANDIDATE` and Gate A. The model gateway may enrich angle, format and urgency, but cannot change the deterministic topic decision or bypass a gate. Topic candidates retain contributing source-item pointers, score breakdowns, machine-readable reason codes and operator-edited artifact versions.

### Research and verification
After Gate A, the Research & Verification Agent builds a primary-source-first plan and a canonical claim/evidence ledger before drafting.

Evidence extraction sits behind a provider-agnostic `ResearchAdapter`. Model-produced excerpts are accepted only when they can be mechanically found in the normalized source text. Source Registry metadata supplies evidence tier and primary/secondary role; deterministic policy computes claim confidence and surfaces contradictions, stale support and unsupported claims.

Sensitive, contradicted or low-confidence research is persisted and routed to a blocked human-review state rather than silently progressing to `VERIFIED`. Research calls, sources, claims and evidence items are explicitly budget-bounded.

### Content generation and vertical packs
The Content Agent reads only verified/human-reviewed research and the canonical claim/evidence ledger. A versioned `VerticalPack` supplies audience, locale, format, voice, prohibited patterns, source rules and SEO behavior.

The model may generate prose and structured factual-assertion references, but Editorial OS resolves claim keys against the ledger and constructs citations itself. Unknown factual assertions are persisted as unsupported rather than silently promoted.

Drafts persist the exact research brief, editorial brief, vertical-pack snapshot, locale/format, structured sections, SEO metadata, citations and revision ancestry. Operator revision creates a new draft version and preserves prior provenance.

### Creative assets
The Creative Agent converts a versioned draft into a versioned `AssetManifest`. Text-only manifests are valid when the vertical pack does not require visuals, so the workflow never invents placeholder images simply to satisfy a state transition.

Visual planning and asset materialization are separate provider-agnostic boundaries. The manifest preserves origin, provenance, generation metadata, source/license data, rights status, variants and a typed Gate-B approval snapshot containing exact draft/manifest/asset versions.

Rights are aggregated conservatively: unresolved rights remain visible for QA/human review, while restricted rights block the workflow.

### Editorial QA
The Editorial QA Agent runs after `ASSETS_READY` and before Gate B. Deterministic checks own factual support, freshness, contradiction handling, confidence thresholds, asset rights and vertical-pack rules. The model-facing QA adapter is limited to semantic consistency checks such as headline/body alignment, asset/text alignment and editorial quality.

Each QA execution persists a versioned `EditorialQAReview` with `PASS | REVISE | BLOCK`, structured findings, policy rule references and an exact snapshot of draft, manifest, asset, claim and evidence identities. `PASS` advances to `QA_PASSED`; `REVISE` returns to `DRAFTED`; `BLOCK` enters `BLOCKED`.

High-risk content remains human-approval-required regardless of model confidence. A semantic model finding can request revision, but model output cannot waive deterministic evidence, risk or rights rules.

### Model gateway
Agents call the provider-independent `ModelGateway`, never a provider SDK. A task-specific `ModelPolicy` chooses the route, the PostgreSQL `BudgetLedger` reserves run/agent spend before the call, and all structured output is validated before it can enter canonical state.

LiteLLM 1.101.x is the first model adapter. Provider/model identifiers remain configuration and usage is recorded in Editorial OS PostgreSQL rather than relying on provider dashboards.

### Observability
Observability is derived, best-effort output. PostgreSQL remains the system of record for workflow actions, audit decisions and model usage.

The shared correlation contract is `request_id + workflow_run_id + agent_id + call_key`. Langfuse receives deterministic run-correlated LLM traces/evaluations, while PostHog receives personless product/editorial events. Structured application logs carry the same correlation IDs and apply credential redaction before serialization.

Telemetry sinks fail independently and may be disabled independently. A telemetry outage cannot change or roll back a canonical workflow result.

### Provider adapters
All external systems sit behind explicit interfaces. Initial candidates:
- RSSHub / Crawl4AI for source acquisition;
- LiteLLM for model routing;
- Langfuse v4 for LLM tracing/evaluation;
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

Every workflow mutation carries a stable `action_key`. The `workflow_actions` ledger has a unique `workflow_run_id + action_key` constraint, so duplicate event delivery reconciles to a no-op and conflicting reuse of a key fails closed.

Every remote side effect also receives a stable idempotency key derived from the workflow run and action identity. Before a remote write the adapter inspects owned state; retries reconcile rather than duplicate.

## Durable gate checkpoints

LangGraph uses a dedicated PostgreSQL `langgraph` schema for checkpoint tables. A workflow run maps to thread `workflow:<uuid>`.

Because a node containing `interrupt()` re-executes from its beginning when resumed, gate nodes perform no irreversible write before the interrupt. Gate decisions are committed only after resume through the canonical WorkflowEngine.

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
