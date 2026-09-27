# Roadmap

## MVP outcome

A trusted source signal can travel through discovery, verification, drafting, QA and all three human gates, then become a Payload draft/publication with a distribution preview and an analytics event. The entire run remains auditable and retry-safe.

## Delivery phases

### Discovery
Freeze the product contract, RAIDER invariants, provider boundaries, risk classes and Adopt/Adapt/Learn/Build decisions.

### Foundation
Introduce the Python API/runtime, PostgreSQL schema, shared contracts, migrations, test harness and local developer environment without breaking the AppFactory React baseline.

### Orchestration
Implement durable workflow state, retries, idempotency, policy/risk evaluation and the three human gates.

### Agents
Implement the seven agent capabilities progressively from Scout to Publishing & Growth. Agents return structured contracts; they do not mutate global workflow state directly.

### Editorial Safety
Introduce evidence/claim tracking, confidence rules, unsupported-claim detection, source hierarchy, sensitive-topic routing and editorial style QA.

### Integrations
Wire external providers through replaceable adapters: ingestion, model gateway, tracing, CMS, distribution, analytics and optional rich media.

### Pilot
Run the first real vertical pack against Trigenys Insight in staging. Measure operator effort, failure rate, article quality, cost and duplicate prevention.

### Release
Validate a second materially different consumer to prove reuse. Document deployment, recovery, backup, secrets and upgrade paths.

## Explicit non-goals for first MVP

- fully autonomous publication for sensitive topics;
- every social network;
- a marketplace of third-party agents;
- video-first generation before the text/image pipeline is stable;
- hardcoding a GL, anime or Trigenys-specific worldview into the core.
