# Trigenys Editorial OS

> Multi-agent editorial operating system for running a small, auditable AI-assisted newsroom from source discovery to publication and growth.

Trigenys Editorial OS is a reusable editorial automation platform. It is intentionally **vertical-agnostic**: Trigenys Insight, a future GL media product, anime, gaming, cyber watch or startup coverage should be configuration and policy packs, not forks of the engine.

## Product target

The MVP turns a source signal into a publishable, traceable draft through seven specialized agents, one deterministic workflow orchestrator and three configurable human approval gates.

```text
Sources
  ↓
Scout
  ↓
Editorial Intelligence
  ↓
Research & Verification
  ↓
Content
  ↓
Creative
  ↓
Editorial QA
  ↓
Publishing & Growth
  ↓
Performance feedback
```

Human gates start at:
1. topic approval;
2. article + asset approval;
3. publication approval.

They may later be relaxed per vertical, risk class and confidence threshold.

## Architecture direction

- **Console:** React 19 + TypeScript + Vite
- **Agent/API runtime:** Python + FastAPI + LangGraph
- **Persistence:** PostgreSQL
- **LLM gateway:** LiteLLM adapter
- **Research/ingestion adapters:** RSSHub, Crawl4AI; evaluate GPT Researcher/STORM patterns
- **Observability:** Langfuse + PostHog
- **CMS:** Payload adapter
- **Workflow/integration edge:** n8n
- **Distribution:** Postiz adapter
- **Rich media:** Remotion adapter, post-MVP unless required by a pilot

These are adapter boundaries, not hardcoded dependencies. RAIDER requires the core to remain reusable, agnostic, idempotent, durable, engineering-grade and retroactive.

## Delivery model

The repository is provisioned by **Trigenys AppFactory** and uses **AppFactory Project Automation** for backlog/project synchronization through the zero-PAT OIDC broker.

Development proceeds issue-by-issue. Every issue has a verifiable Proof of Done and explicit dependencies.

Read:
- [Product contract](docs/product-contract.md)
- [Risk & confidence policy](docs/risk-and-confidence.md)
- [MVP success metrics](docs/mvp-metrics.md)
- [Architecture](docs/architecture.md)
- [Architecture Decision Records](docs/adr/README.md)
- [Roadmap](docs/roadmap.md)
- [PERT](docs/pert.md)
- [Proof of Done](docs/proof-of-done.md)
- [Reuse-first ecosystem reconnaissance](docs/ecosystem-reconnaissance.md)
- [Failure memory](docs/engineering/lessons-learned.md)

## Baseline

- React 19
- TypeScript
- Vite
- Node.js 24 CI
- AppFactory Project Automation
- AppFactory webapp blueprint marker

## Development

```bash
npm install
npm run dev
```

Validate the current frontend baseline with:

```bash
npm run typecheck
npm run build
```

Backend commands will be documented when the Foundation issue introduces the API runtime.

## Status

**Discovery / product contract.** The MVP contract, risk/confidence model, human gates and initial architecture decisions are versioned. Implementation starts only after the Discovery contract is accepted through Issue #1.
