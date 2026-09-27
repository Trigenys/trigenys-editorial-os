# MVP success metrics

Metrics are used to determine whether the Editorial OS reduces operator workload without trading away provenance or reliability.

## 1. Operator effort

**Metric:** manual actions per completed editorial run.

Count:
- Gate A decision;
- Gate B decision;
- Gate C decision;
- manual research intervention;
- manual factual correction;
- manual rewrite request;
- manual publication recovery.

**Pilot target:** median <= 6 actions per completed run, including the three mandatory gates.

The target is intentionally not "zero human touches"; human authority is part of the MVP product.

## 2. Factual support coverage

**Metric:** supported material claims / total material factual claims in the Gate-B candidate.

**MVP target:** 100%.

A claim without evidence must be marked as opinion/analysis, removed, or block QA. "Plausible" is not supported.

## 3. Duplicate side-effect rate

**Metric:** duplicate owned CMS publications, assets or distribution posts caused by retry/replay.

**MVP target:** 0.

This is a hard correctness metric, not a soft quality target.

## 4. Topic duplicate rate

**Metric:** topic candidates that should have been clustered with an existing active topic but were proposed separately.

**Pilot target:** < 5% after manual review of the pilot sample.

## 5. Cost visibility and budget adherence

**Metrics:**
- model/tool cost per run;
- cost by agent;
- cost per completed article;
- aborted cost;
- budget-limit events.

**MVP target:**
- 100% of chargeable model/tool executions correlated to a run/agent;
- 0 runs continue after a hard configured budget ceiling is reached.

The absolute monetary budget is vertical/configuration-specific and must not be hardcoded in the core.

## 6. Publication failure rate

**Metric:** publication attempts that end in terminal failure after allowed retry/reconciliation.

**Pilot target:** < 5%.

Provider outage may cause delayed publication, but it must not corrupt canonical workflow state.

## 7. Recovery rate

**Metric:** retryable failed runs that successfully resume without starting a duplicate editorial run.

**Pilot target:** >= 95% for injected retryable failures covered by the test plan.

## 8. Audit completeness

**Metric:** completed runs with source provenance, claim/evidence links, gate decisions, versions, correlation ID and publication receipt.

**MVP target:** 100%.

## 9. Unsupported-claim escape rate

**Metric:** published material factual claims later found to have had no supporting evidence in the stored ledger at publication time.

**MVP target:** 0.

This measures process escape, not whether later real-world facts change.

## 10. Second-consumer portability

**Metric:** core code changes required only because a second vertical has a different editorial identity/source mix.

**Release target:** 0 vertical-name branches in core and no fork.

Provider adapter additions are allowed; vertical-specific behavior belongs in configuration/packs.

## Pilot reporting

The Trigenys Insight staging pilot should report at minimum:
- number of completed/rejected/blocked runs;
- median manual actions;
- support coverage;
- duplicate rate;
- cost distribution;
- latency distribution;
- publication failures/recovery;
- QA revision/block reasons;
- top operator interventions.

Targets may be tightened after the first measured pilot, but relaxing a hard invariant requires an ADR.
