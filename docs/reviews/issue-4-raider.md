# RAIDER review — Issue #4 durable workflow engine

## Reusable

- Workflow states and actions are editorial-domain concepts, not agent/provider concepts.
- `WorkflowEngine` is an internal protocol; LangGraph is one adapter.
- Stable action keys and gate semantics can be reused by every vertical.

## Agnostic

- Agents cannot mutate canonical state directly.
- LangGraph checkpoint state is not the system of record.
- The gate coordinator depends on the `WorkflowEngine` protocol rather than SQLAlchemy details.
- Provider/CMS/model SDK objects remain outside orchestration contracts.

## Idempotent

- `workflow_actions` enforces `workflow_run_id + action_key` uniqueness.
- Exact duplicate delivery returns `applied=false`.
- Reusing an action key with different content fails closed.
- Gate resumes use the same action ledger.
- Second identical reconcile is therefore a no-op.

## Durable / Non-regressive

- Workflow state carries an explicit monotonic `state_version`.
- Retryable/block states persist `resume_status`.
- LangGraph checkpoints use PostgreSQL, not process memory.
- Checkpoint tables are isolated in the `langgraph` schema.
- Existing domain/audit schema remains canonical.

## Engineering-grade

- Row-level locking serializes mutations of one workflow run.
- Transition legality is explicit and unit-tested.
- Invalid transitions write nothing.
- Gate A/B/C approval/rejection/revision routes are deterministic.
- Retryable and terminal failures are explicit states.
- Append-only `workflow_actions` create an ordered action ledger.
- LangGraph node re-execution semantics are accounted for by forbidding side effects before interrupt.
- Strict msgpack checkpoint deserialization is enabled.

## Reuse-first

Adopt/Adapt:
- LangGraph 1.2.x — durable graph/runtime and human interrupt primitive.
- langgraph-checkpoint-postgres 3.1.x — production PostgreSQL checkpointer.

Build:
- canonical workflow transition policy;
- gate policy;
- action idempotency;
- audit/state ownership;
- retry/resume semantics.

Those are differentiating product rules and must remain ours.

## Retroactive

- The engine is additive over the Issue #3 canonical schema.
- Existing workflow rows migrate with `state_version=0`.
- LangGraph can be replaced later without rewriting canonical state or action history.
- Gate policy can become less strict later without changing workflow state names.

## Issue #4 Proof of Done mapping

- [x] State transitions are unit/integration tested.
- [x] Invalid transitions fail closed and write no action.
- [x] A paused gate survives coordinator/checkpointer reconstruction.
- [x] Duplicate delivery does not duplicate transitions.
- [x] Gate A, Gate B and Gate C block progression in the MVP.
- [x] Gate policy can vary by vertical/risk when the MVP lock is disabled.
- [x] MVP lock keeps all three gates mandatory.
- [x] Retryable and terminal failure states are implemented.
- [x] Stable action keys are persisted.
- [x] Operator revision routing is implemented.
- [x] Second identical reconcile is a no-op.
