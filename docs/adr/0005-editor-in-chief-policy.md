# ADR-0005 — Editor-in-Chief as deterministic policy, not an eighth agent

**Status:** Accepted  
**Date:** 2026-09-28

## Context

The editorial workflow needs a supervisory role that decides when work can advance, when humans must approve, and when execution must stop. Implementing this as another conversational agent would allow probabilistic text generation to control policy and workflow truth.

## Decision

The Editor-in-Chief role is the composition of:
- workflow state machine;
- gate engine;
- risk/confidence policy;
- budget/retry rules;
- authorization checks;
- audit requirements.

It is not an LLM persona and not counted among the seven agents.

## Consequences

Positive:
- policy is testable;
- safety/risk rules fail closed;
- approvals and budgets cannot be "persuaded" by generated text;
- easier audit and replay.

Costs:
- policies must be explicitly modeled rather than hidden in prompts.

## Guardrails

- agent output is treated as input data, not authority;
- high risk cannot be downgraded by model confidence alone;
- Gate C is mandatory in MVP;
- policy changes are versioned and auditable.
