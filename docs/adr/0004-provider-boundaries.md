# ADR-0004 — Ports/adapters for all external providers

**Status:** Accepted  
**Date:** 2026-09-28

## Context

The planned stack includes RSSHub, Crawl4AI, LiteLLM, Langfuse, Payload, n8n, Postiz, PostHog and later Remotion. Hard-coding these into domain models would turn implementation choices into irreversible product constraints.

## Decision

All external systems are reached through narrow provider interfaces/ports with adapter implementations.

Initial decisions from ecosystem reconnaissance:
- RSSHub — Adapt
- Crawl4AI — Adopt/Adapt
- GPT Researcher — Learn/Adapt
- STORM — Learn
- LangGraph — Adapt
- LiteLLM — Adapt
- Langfuse — Adopt/Adapt
- Payload — Adapt
- n8n — Adapt for peripheral workflows only
- Postiz — Adapt
- PostHog — Adopt/Adapt
- Remotion — Adapt later

## Consequences

Positive:
- testing with fakes;
- provider exit strategy;
- vertical neutrality;
- narrower failure domains.

Costs:
- interface design work;
- some provider-specific features may need explicit extension points.

## Guardrails

- no vendor SDK object crosses into domain contracts;
- adapters classify timeout/retry/terminal errors;
- write adapters support idempotency/reconciliation;
- provider-specific secrets never enter vertical packs;
- n8n never owns canonical editorial state.
