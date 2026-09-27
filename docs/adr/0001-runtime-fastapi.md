# ADR-0001 — Split React console + FastAPI service runtime

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

AppFactory provisioned a React/TypeScript/Vite webapp baseline. The Editorial OS also needs an orchestration/API runtime with strong Python support for agent tooling, structured validation, research/extraction libraries and LangGraph.

## Decision

Keep the React console and introduce a separate Python/FastAPI service boundary in the same repository for MVP.

The browser talks to the API. The browser does not own canonical workflow state or provider credentials.

## Consequences

Positive:
- preserves the generated frontend baseline;
- uses Python where the agent ecosystem is strongest;
- lets frontend/backend deploy independently;
- keeps browser permissions narrow.

Costs:
- two runtime toolchains;
- cross-boundary API contracts must be versioned/tested;
- local development needs coordinated startup.

## Guardrails

- provider secrets remain server-side;
- domain contracts are transport-agnostic;
- frontend does not talk directly to LLM/CMS/social providers;
- Node 24 CI remains valid while Python CI is added in Foundation.

## Rejected

- moving all orchestration into the React/Node runtime immediately;
- putting agent execution in the browser;
- replacing the generated React baseline before requirements justify it.
