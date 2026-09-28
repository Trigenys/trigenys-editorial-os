# LangGraph validation for Issue #4

**Validated:** 2026-09-28  
**Runtime line:** LangGraph 1.2.12  
**PostgreSQL checkpointer line:** langgraph-checkpoint-postgres 3.1.2

## Decision

LangGraph remains **accepted behind the internal workflow-engine boundary**.

It satisfies the orchestration mechanics we need for the MVP:

- durable thread-scoped checkpoints;
- PostgreSQL-backed persistence;
- stable `thread_id` identity;
- human-in-the-loop `interrupt()`;
- resume through `Command(resume=...)`;
- recovery after the coordinator/process is reconstructed.

It does **not** own canonical editorial truth.

Canonical truth remains:

- `workflow_runs`;
- `workflow_actions`;
- `gate_decisions`;
- `audit_events`;
- versioned editorial artifacts.

## Important resume behavior

A LangGraph node containing `interrupt()` restarts from the beginning of that node when resumed.

Editorial OS therefore enforces this rule:

> No irreversible write is allowed before an interrupt.

The gate node may read canonical state before `interrupt()`, but the actual GateDecision and workflow transition happen only after resume, through `PostgresWorkflowEngine.decide_gate()`.

Every mutation carries a stable `action_key`, so duplicate resume/event delivery reconciles to a no-op instead of creating a second transition.

## Checkpoint isolation

LangGraph internal checkpoint tables are not mixed with canonical domain tables.

Alembic creates a dedicated PostgreSQL schema:

```text
langgraph
```

The checkpointer connection uses:

```text
search_path=langgraph,public
```

`PostgresSaver.setup()` reconciles its internal tables inside that schema.

The application also enables strict msgpack checkpoint deserialization through:

```text
LANGGRAPH_STRICT_MSGPACK=true
```

## Thread identity

A workflow run maps deterministically to one LangGraph thread:

```text
workflow:<workflow_run_uuid>
```

Reconstructing a coordinator with the same workflow ID and PostgreSQL database therefore points back to the same checkpoint.

## Boundary

```text
LangGraph
  │
  │ pause / resume / checkpoint
  ▼
LangGraphGateCoordinator
  │
  │ typed command
  ▼
WorkflowEngine
  │
  │ validates legal transition + idempotency
  ▼
PostgreSQL canonical state
```

Agents never write `workflow_runs.status` directly.

## Exit test

The Issue #4 integration test:

1. creates a run waiting at Gate A;
2. starts a coordinator and reaches `interrupt()`;
3. closes the checkpointer/coordinator;
4. creates a new checkpointer/coordinator;
5. resumes the same `thread_id`;
6. commits exactly one Gate A approval and reaches `TOPIC_APPROVED`.

That is the minimum evidence required to keep LangGraph as the first orchestration implementation.
