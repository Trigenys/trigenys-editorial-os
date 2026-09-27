# ADR-0002 — LangGraph behind an internal workflow-engine boundary

**Status:** Accepted for MVP, reversible  
**Date:** 2026-09-28

## Context

The product requires resumable state, branches, retries and human checkpoints. It must also avoid coupling canonical business state to one orchestration framework.

## Decision

Adopt/adapt LangGraph as the first orchestration implementation behind an internal `WorkflowEngine` boundary.

Canonical workflow states, transition rules, gate policy, idempotency keys and audit records are Editorial OS domain concepts. LangGraph is an implementation mechanism, not the public product contract.

## Consequences

Positive:
- human-in-the-loop/checkpoint patterns match the product;
- avoids building a full durable graph engine before validating the product;
- broad Python ecosystem compatibility.

Costs:
- framework lifecycle becomes a dependency;
- checkpoint semantics must be reconciled with our own PostgreSQL audit/state model.

## Guardrails

- graph nodes cannot invent new legal workflow states;
- remote side effects go through owned adapters with idempotency;
- domain tests run without LangGraph where practical;
- a failed/paused run must be reconstructable from canonical stored state.

## Exit strategy

If LangGraph cannot satisfy durability, observability or upgrade requirements, replace the adapter while preserving domain states/contracts.
