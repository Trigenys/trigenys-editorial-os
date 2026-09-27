# Proof of Done

Every implementation issue must include issue-specific acceptance criteria plus this common baseline where applicable.

## Common Proof of Done

- [ ] Scope and public contracts are explicit.
- [ ] RAIDER review completed: Reusable, Agnostic, Idempotent, Durable, Engineering-grade, Retroactive.
- [ ] Relevant ecosystem options were evaluated as Adopt / Adapt / Learn / Build.
- [ ] Happy path is covered by automated tests.
- [ ] Failure/retry path is covered where the capability has side effects.
- [ ] A second identical apply/run does not create duplicate owned state.
- [ ] Secrets and private source data are not committed or logged.
- [ ] Errors are actionable and include a stable correlation/run identifier.
- [ ] Observability exists at the boundary appropriate to the risk.
- [ ] Typecheck/build/tests relevant to the change are green.
- [ ] Documentation/ADR is updated if the public contract or architecture changed.
- [ ] Significant failures/near misses discovered during the work are recorded in Failure Memory.
- [ ] Evidence proving the issue is done is linked in the PR or issue.

## Agent-specific Proof of Done

An agent is not done because it can generate plausible prose. It is done when:
- its input/output schema is versioned and validated;
- deterministic policy remains outside the model prompt where practical;
- unsupported/invalid output fails closed or enters a review path;
- model/provider is replaceable behind an adapter;
- token/cost/time usage is observable;
- fixtures allow tests without paid model calls;
- a real-provider smoke test exists separately from deterministic unit tests.

## Integration-specific Proof of Done

An external adapter must:
- expose a narrow interface;
- implement timeouts and bounded retries;
- classify retryable vs terminal failures;
- support idempotency/reconciliation for writes;
- avoid leaking provider-specific objects into the domain core;
- document required permissions and data handling.
