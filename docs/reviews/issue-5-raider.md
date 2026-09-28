# RAIDER review — Issue #5 model gateway

## Reusable

- `ModelClient` is a narrow protocol shared by all agents.
- `ModelPolicy` routes by task rather than vertical or provider name.
- The deterministic fake can drive every future agent test.

## Agnostic

- Provider SDK imports are isolated to `model_gateway/adapters`.
- Core requests/responses use Editorial OS contracts.
- Model identifiers are configuration, not branching logic.
- Two materially different provider route strings are exercised through the same LiteLLM adapter contract in CI.

## Idempotent

- Every metered call has a stable `call_key`.
- `workflow_run_id + call_key` is unique in PostgreSQL.
- Duplicate call reservation fails before another paid call can leave the process.
- Repair calls use deterministic suffixes of the parent call key.

## Durable / Non-regressive

- Model usage is persisted independently of provider dashboards.
- In-flight reservations count against budget.
- Unknown failure cost is conservatively retained.
- Existing workflow/domain migrations remain unchanged; Issue #5 is additive as revision `0004`.

## Engineering-grade

- Per-run and per-agent budget ceilings are checked transactionally under a workflow-row lock.
- Tokens, cost, latency, route, task, run and agent IDs are persisted.
- Invalid structured output receives only bounded repair attempts.
- A second invalid response fails closed.
- Actual-cost overruns are recorded and withheld.
- CI performs no paid model call.

## Reuse-first

**Adopt/Adapt:** LiteLLM 1.101.x as the first provider adapter.

**Build:** task policy, canonical budget ledger, output-validation policy and deterministic doubles because these are product invariants that must remain provider-independent.

## Retroactive

- The gateway does not require existing agents to choose a provider SDK.
- Future provider migration changes route configuration/adapter only.
- Usage history remains readable even if LiteLLM is later replaced.
- New task classes can be added without changing existing routes.

## Issue #5 Proof of Done mapping

- [x] Core code imports no vendor SDK directly.
- [x] CI runs entirely on deterministic fake responses.
- [x] Two provider configurations satisfy the same adapter interface in CI.
- [x] Run budget breach prevents the provider call.
- [x] Agent budget breach prevents the provider call.
- [x] Actual-cost overrun is recorded and output is withheld.
- [x] Invalid structured output is repaired once by default, then fails closed.
- [x] Usage is correlated to workflow run, agent, task, route and call key.
- [x] Token, cost and latency metadata are persisted.
