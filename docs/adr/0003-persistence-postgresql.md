# ADR-0003 — PostgreSQL as canonical product state

**Status:** Accepted  
**Date:** 2026-09-28

## Context

The Editorial OS needs relational integrity across workflow runs, claims, evidence, gates, versions, publications, idempotency keys and performance references.

## Decision

Use PostgreSQL as the canonical system of record for product/domain state.

Large raw documents and binary assets may later live in object storage, referenced by stable metadata from PostgreSQL.

Langfuse, PostHog, Payload, n8n and provider dashboards are not canonical product state.

## Consequences

Positive:
- transactional integrity;
- migrations and relational constraints;
- good audit/query capability;
- provider-independent ownership.

Costs:
- schema design/migrations are product responsibilities;
- large raw blobs should not be stored indiscriminately.

## Guardrails

- migrations are versioned;
- gate decisions/version links are durable;
- idempotency ownership is stored canonically;
- deletion/retention policy applies to fetched content;
- adapters persist external IDs/receipts, not vendor objects.
