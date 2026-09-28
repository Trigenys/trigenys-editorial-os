# RAIDER review — Issue #6 observability

## Reusable

- One correlation contract is shared by API, orchestrator and model gateway.
- Telemetry contracts are provider-independent.
- The same sinks can instrument every future editorial agent.

## Agnostic

- Langfuse and PostHog are adapters behind `TelemetrySink`.
- Canonical audit/model usage remain PostgreSQL state.
- Local development can use an empty hub or `NoopTelemetrySink`.
- Raw model IO is not required for operational observability.

## Idempotent

- Telemetry correlation reuses stable workflow/action/call identifiers.
- Model cost truth is read from the canonical idempotent model-usage ledger.
- Telemetry never creates workflow transitions or provider side effects.

## Durable / Non-regressive

- Observability outages cannot roll back canonical workflow state.
- Disabled adapters require no external service.
- Existing workflow and model-gateway behavior works with the default empty hub.
- No database migration is required for telemetry because canonical records already exist.

## Engineering-grade

- JSON structured logs carry correlation fields.
- Credentials are recursively/textually redacted.
- Error categories are normalized.
- Langfuse uses deterministic run-derived trace IDs.
- PostHog events are personless.
- Sinks fail independently.
- Cost, token usage and latency are correlated to run/agent/call key.
- Model prompt/output export is opt-in rather than default.

## Reuse-first

**Adopt/Adapt:**
- Langfuse Python 4.15.x for OpenTelemetry-based LLM traces and evaluation scores.
- PostHog Python 7.60.x for operational/product/editorial events.

**Build:**
- correlation contract;
- redaction rules;
- error taxonomy;
- failure-isolating telemetry hub;
- canonical-vs-derived-data boundary.

These rules are product invariants and cannot be delegated to observability vendors.

## Retroactive

- Existing workflow/model rows immediately provide the correlation backbone.
- Future agents only need to preserve run/agent/call identifiers.
- Either telemetry vendor can be replaced without changing canonical schemas.
- Additional sinks can be appended to the hub without modifying business logic.

## Issue #6 Proof of Done mapping

- [x] One workflow can be correlated end-to-end by run ID.
- [x] API, orchestrator and model gateway share correlation context.
- [x] Secrets/raw credentials are redacted from structured logs and telemetry properties.
- [x] Product audit/model usage state remains PostgreSQL canonical state.
- [x] Telemetry sink failures do not roll back workflow state.
- [x] Langfuse and PostHog are independently configurable.
- [x] Local/no-op telemetry is available.
- [x] Model cost, tokens and latency are visible per agent/run.
- [x] Raw prompt/response capture is disabled by default.
