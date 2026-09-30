# Issue #15 — Operator Console RAIDER review

## Reusable
The operator surface consumes a provider-neutral read model. The browser sees workflow, editorial, evidence, cost and delivery state without importing Payload, Postiz, n8n, PostHog or model-provider SDK concepts.

## Agnostic
All consequential mutations go through the existing workflow engine. The console does not write gate rows, workflow status or recovery state directly.

## Idempotent
Gate action keys are derived from workflow id, state version, gate, canonical artifact and outcome. Recovery action keys are derived from workflow id, state version and legal recovery action. Duplicate browser submissions therefore converge on workflow-engine idempotency instead of creating parallel state changes.

## Durable / non-regressive
The console is an additive API/read-model layer. Existing agents, publishing and distribution services remain authoritative. Operator UI failure cannot roll back canonical publication or delivery state.

## Engineering-grade
- Gate artifacts are resolved on the server from the canonical current workflow state.
- The API request cannot supply an artifact id/version, preventing the browser from approving an arbitrary object.
- Gate legality remains enforced by `PostgresWorkflowEngine.decide_gate()`.
- Recovery is limited to `FAILED_RETRYABLE -> RETRY` and `BLOCKED -> RESUME`; the engine validates the final transition.
- Every human decision records actor, time, artifact type/id/version and reason through existing audit/governance models.
- The operator read model deliberately omits runtime settings, provider credentials, workflow context, publication receipts and distribution receipts.
- No provider token is sent to the browser.
- Responsive layouts preserve approval controls on tablet/mobile widths.

## Retroactive
Existing workflow rows can appear in the console without a migration. Existing published/distributed runs remain inspectable, including historical gate decisions, timeline and model-usage cost.

## Proof-of-Done mapping
- Single control surface: queue + run detail + evidence + draft + assets + delivery + timeline in `src/App.tsx`.
- Backend gate enforcement: `test_gate_action_resolves_canonical_artifact_server_side_and_audits_actor` and `test_operator_cannot_decide_a_gate_from_a_non_gate_state`.
- Approval audit identity/version: same gate test validates actor and canonical artifact version.
- Failure recovery: `test_retryable_run_can_be_recovered_from_console` plus illegal-state rejection.
- Mobile/tablet approval usability: responsive breakpoints at 780px and 520px keep controls full-width/tappable.
- Secret-safe browser contract: `test_operator_queue_filters_and_never_exposes_run_context`.
- Basic filtering: vertical, status, risk, topic decision and updated date range are server-side filters.

## Operational boundary
This console is the human control plane, not a replacement workflow scheduler. Agents and adapters continue to execute through their domain services; the operator can inspect state, make mandatory human decisions and recover legal failure states without opening provider dashboards.
