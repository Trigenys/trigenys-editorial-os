# Observability and correlation

Issue #6 adds operational visibility without moving canonical product truth out of PostgreSQL.

## Principle

Observability is **derived, best-effort output**.

Canonical state remains:

- `workflow_runs`;
- `workflow_actions`;
- `gate_decisions`;
- `audit_events`;
- `model_usage_records`;
- versioned editorial artifacts.

Langfuse and PostHog may be unavailable, delayed or disabled without changing the legal result of a workflow transition.

## Correlation contract

Every layer uses the same correlation vocabulary:

```text
request_id
workflow_run_id
agent_id
call_key
```

The stable cross-process correlation ID is `workflow_run_id` whenever a run exists.

The API middleware accepts:

- `X-Request-ID`;
- `X-Workflow-Run-ID`.

It returns:

- `X-Request-ID`;
- `X-Correlation-ID`.

The model gateway binds `workflow_run_id + agent_id + call_key`. The observed workflow-engine wrapper binds `workflow_run_id + action_key`.

## Structured logs

Application logging uses JSON records with correlation fields.

Sensitive keys are recursively redacted, including:

- authorization;
- cookies;
- passwords;
- secrets;
- tokens;
- API keys;
- credentials;
- private keys.

Text redaction also removes:

- Bearer tokens;
- common secret prefixes;
- `token=...` / `password=...` style assignments;
- passwords embedded in connection URLs.

Do not bypass structured logging with raw credential dumps.

## Error taxonomy

Operational errors are normalized to:

- `budget`;
- `validation`;
- `provider`;
- `persistence`;
- `policy`;
- `telemetry`;
- `internal`.

Telemetry records contain error category/type and a bounded, redacted message where appropriate. They do not contain model chain-of-thought.

## Langfuse adapter

Editorial OS uses the Langfuse Python v4 line.

The adapter records:

- deterministic trace ID derived from `workflow_run_id`;
- agent;
- task;
- call key;
- route;
- provider model;
- token usage;
- cost;
- estimated-cost flag;
- status/error classification.

Evaluations are attached to the same deterministic workflow trace through Langfuse scores.

### Model IO

Raw prompt/response capture is **off by default**.

Enable only with:

```text
EDITORIAL_OS_LANGFUSE_CAPTURE_MODEL_IO=true
```

Even when enabled, the generic redaction layer runs before IO is handed to Langfuse.

## PostHog adapter

PostHog receives personless operational/editorial events.

A workflow uses:

```text
distinct_id = workflow:<workflow_run_id>
```

and every server event sets:

```text
$process_person_profile = false
```

This avoids turning workflow IDs into user/person profiles.

Model-call events expose run/agent/task/model/cost/token/latency metadata, not raw prompts or responses.

## Independent switches

```text
EDITORIAL_OS_LANGFUSE_ENABLED=false
EDITORIAL_OS_POSTHOG_ENABLED=false
```

Each adapter has its own credentials and host.

Missing credentials on an enabled optional adapter degrade that adapter to disabled-with-warning rather than taking down the API.

For local development and deterministic tests, use `NoopTelemetrySink` or an empty `ObservabilityHub`.

## Failure isolation

`ObservabilityHub` invokes every sink independently.

If a sink raises:

1. the failure is redacted and written to local structured logs;
2. remaining sinks still receive the event;
3. the original workflow/model operation keeps its canonical outcome.

Telemetry delivery is never part of the PostgreSQL transaction that defines workflow truth.

## Cost and latency

Canonical model usage is still `model_usage_records`.

Telemetry mirrors:

- `workflow_run_id`;
- `agent_id`;
- `call_key`;
- input/output tokens;
- actual or estimated cost;
- latency;
- route/model;
- success/failure/budget status.

This lets dashboards aggregate operational cost and latency per run or per agent without relying on provider dashboards as the source of record.
