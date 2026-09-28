# Model gateway

Issue #5 defines the only model-calling boundary used by Editorial OS agents.

## Decision

The core owns a narrow `ModelClient` protocol. LiteLLM is the first adapter, not the domain contract.

```text
Agent
  │
  ▼
ModelGateway
  ├── task-specific ModelPolicy
  ├── BudgetLedger
  ├── structured-output validator
  └── ModelClient protocol
          │
          ▼
      LiteLLM adapter
          │
          ├── OpenAI-compatible route
          ├── Anthropic route
          ├── local/self-hosted route
          └── future providers
```

No agent or domain module imports provider SDKs.

## Task-specific policy

A `ModelPolicy` maps each `ModelTask` to a `ModelRoute`.

The MVP task classes are:

- `editorial_intelligence`;
- `research_verification`;
- `content_drafting`;
- `creative_brief`;
- `editorial_qa`;
- `growth_analysis`.

This means a cheap/fast model can serve classification while a stronger model serves research or drafting without changing agent code.

A route owns:

- logical route name;
- provider/model identifier understood by the adapter;
- maximum reserved cost for one call;
- JSON-mode capability;
- timeout;
- bounded retry count.

## Budget model

Every provider call is correlated by:

```text
workflow_run_id
agent_id
task
call_key
route_name
provider_model
```

Before a provider call, `BudgetLedger.reserve()`:

1. locks the workflow run;
2. loads current model spend;
3. counts completed actual cost and in-flight reservations;
4. checks the per-run ceiling;
5. checks the per-agent ceiling;
6. writes a `RESERVED` usage record only if both checks pass.

A rejected reservation means **no provider call happens**.

### Conservative accounting

If a provider returns no reliable cost, the configured reservation becomes the recorded estimated cost.

If a provider call raises without returning usage, the reservation is retained as estimated spend. This may over-count failures, but it prevents unknown-cost calls from silently bypassing ceilings.

If actual returned cost exceeds the reserved amount and pushes the run/agent above budget, the usage record is committed as `COMPLETED_OVER_BUDGET` and the model output is withheld from the caller.

## Structured output

Structured model work is always validated by Pydantic.

Flow:

```text
provider output
    │
    ▼
Pydantic validation
    │
    ├── valid ──► typed object
    │
    └── invalid
          │
          ▼
   bounded repair call
          │
          ▼
   Pydantic validation
          │
          ├── valid ──► typed object
          └── invalid ──► StructuredOutputError
```

The default repair budget is one attempt. Repair is itself a separate metered model call and therefore consumes run/agent budget.

No malformed model output is silently coerced into canonical editorial state.

## Deterministic CI

`DeterministicFakeModel` accepts scripted responses and fixed token/cost/latency metadata.

CI therefore verifies:

- typed structured output;
- repair and fail-closed paths;
- usage correlation;
- run budget;
- agent budget;
- actual-cost overrun;
- multiple provider route identifiers through the LiteLLM adapter;

without network access or paid model calls.

## LiteLLM evaluation

LiteLLM is accepted as the first adapter because it provides one completion interface across many providers, normalized usage metadata, provider model routing and cost metadata.

Editorial OS deliberately does **not** delegate its canonical run/agent budget policy to LiteLLM. Our budget ledger must remain reconstructable from the same PostgreSQL system of record as workflow state.

The adapter is therefore replaceable without changing:

- agent contracts;
- task policy;
- budget records;
- structured validation;
- workflow audit correlation.
