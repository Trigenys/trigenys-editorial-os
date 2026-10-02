# Failure memory

This file is the default RAIDER failure-memory location for Trigenys Editorial OS.

## Entry template

### YYYY-MM-DD — Short title

**Category**  
Architecture / security / CI-CD / data / dependency / infrastructure / release / automation / UX / performance / testing / process

**Context**  
What we were trying to do.

**Symptom / near miss**  
What failed or almost failed.

**Impact**  
What was affected.

**Root cause**  
Why it happened, not only the visible symptom.

**Resolution**  
What fixed the immediate problem.

**Prevention**  
Test, guardrail, validation, checklist, architecture change or documentation added to reduce recurrence.

**Generalized lesson**  
What another project/consumer should learn from this.

**RAIDER impact**  
Any new or strengthened rule/pattern.


### 2026-09-27 — Backlog dependency references were emitted as `#undefined`

**Category**  
Automation / process

**Context**  
The initial Editorial OS backlog was created programmatically through the GitHub connector.

**Symptom / near miss**  
The issues themselves were created, but a connector response-shape assumption caused dependency references in several issue bodies to be rendered as `#undefined`.

**Impact**  
The canonical backlog existed, but issue-level dependency text was temporarily unreliable. The correct graph is preserved in `BACKLOG.md`.

**Root cause**  
The automation assumed the created issue number was exposed at a specific normalized payload field instead of validating the mutation result before chaining dependent writes.

**Resolution**  
Use the canonical returned issue URL as the fallback identifier and keep the intended dependency graph in a versioned repository document.

**Prevention**  
Future backlog automation must validate the identifier after every create mutation. If the normalized numeric field is missing, parse and validate `/issues/<number>` from the canonical URL; fail closed if neither is available.

**Generalized lesson**  
Never derive downstream state from an unvalidated connector response shape.

**RAIDER impact**  
Strengthens Idempotent and Engineering-grade: validate mutation outputs before dependent writes.


### 2026-09-27 — Concurrent initial Issue events created duplicate GitHub Projects

**Category**  
Automation / CI-CD / architecture

**Context**  
The initial backlog opened 18 Issues quickly while AppFactory Project Automation was also bootstrapping the repository's organization Project.

**Symptom / near miss**  
Concurrent first-run workers created Projects #6 and #7 with the same title. Early runs then failed with `Name has already been taken` and stale single-select option IDs. Later runs converged on Project #7.

**Impact**  
The active board became healthy, but Project #6 remains an orphan/partial duplicate requiring administrative cleanup. Issues #1 and #4 also needed an explicit user-authenticated resync into Project #7.

**Root cause**  
Normal synchronization concurrency is scoped per Issue/PR, which is correct after bootstrap, but Project creation/schema bootstrap mutates shared repository-level state and was not serialized as a shared critical section.

**Resolution**  
Project #7 was retained as the canonical board. Missing initial Issues were resynchronized through user-authenticated `issues: edited` events. Platform bug EagleFox31/appfactory-project-automation#68 records the permanent fix.

**Prevention**  
Serialize or otherwise make the initial Project creation/bootstrap transaction concurrency-safe while preserving issue-scoped concurrency after convergence. Add a burst regression test.

**Generalized lesson**  
Concurrency granularity must match mutation ownership: item-level locks are insufficient when initialization creates shared parent resources.

**RAIDER impact**  
Strengthens Idempotent, Durable and Retroactive behavior for greenfield bootstrap under real event bursts.


### 2026-09-30 — Remote social delivery cannot treat every timeout as a normal retry

**Category**  
Architecture / reliability / automation

**Context**  
Issue #14 adds Postiz-backed social distribution with retry-safe owned jobs.

**Symptom / near miss**  
A naive retry policy would re-send a social mutation whenever the HTTP client timed out or received an ambiguous server failure.

**Impact**  
The canonical article would remain safe, but the same social post could be published twice because a provider can accept a request even when the client never receives the success receipt.

**Root cause**  
Local idempotency protects database rows, not an external provider that does not document a matching idempotency guarantee for the mutation.

**Resolution**  
Distribution jobs now enter `DISPATCHING` before the remote mutation. Explicit pre-delivery rejection can become `FAILED_RETRYABLE`; ambiguous outcomes remain `DISPATCHING` and require reconciliation before another mutation.

**Prevention**  
Every new remote mutation adapter must classify failures as safe-to-retry, terminal, or ambiguous. Ambiguous mutations fail closed and must not be automatically replayed.

**Generalized lesson**  
Exactly-once behavior across an external API is a protocol property, not something a local unique constraint can magically provide.

**RAIDER impact**  
Strengthens Idempotent, Durable and Engineering-grade remote mutation rules.


### 2026-10-02 — Repeated manual fixes for Ruff import ordering wasted CI cycles

**Category**  
CI-CD / testing / process

**Context**  
Issue #35 added staging deployment utilities, including a new Python script under `scripts/staging/`.

**Symptom / near miss**  
The same Ruff `I001` import-ordering failure was fixed manually more than once, but each edit guessed the formatter's grouping instead of reproducing Ruff's exact fix locally first.

**Impact**  
The code change itself was trivial, but several CI runs were wasted and progress on the staging deployment was delayed.

**Root cause**  
The repair loop treated a deterministic formatter/linter failure as a code-review judgment call. The authoritative tool output was available, but the workflow did not require applying or previewing Ruff's own fix before pushing another commit.

**Resolution**  
The import block was changed to the exact ordering Ruff accepts and CI passed.

**Prevention**  
For deterministic lint failures, do not hand-guess formatting. Run the exact repository command locally first. For Ruff `I001`, use `python -m ruff check <path> --fix` on the working tree, inspect the diff, then rerun the full CI lint command before committing. If local execution is unavailable, derive the exact edit from Ruff's suggested diff and verify once before pushing.

**Generalized lesson**  
When a tool can deterministically produce the correct transformation, use the tool as the source of truth instead of iterating by intuition.

**RAIDER impact**  
Strengthens Engineering-grade and Retroactive behavior: convert repeated CI friction into an explicit repair rule so the same class of failure costs one iteration, not several.


### 2026-10-02 — A separate push-triggered deploy could race ahead of CI

**Category**  
CI-CD / release / infrastructure

**Context**  
Issue #35 introduced a standalone staging deployment workflow beside the repository CI workflow.

**Symptom / near miss**  
The first design listened directly to pushes on `main`. Once automatic staging deployment was enabled, GitHub could start CI and deployment concurrently for the same commit.

**Impact**  
A revision could theoretically reach staging before its API, web and staging-artifact checks had completed. Documentation-only merges could also rebuild and redeploy unchanged product surfaces.

**Root cause**  
Deployment eligibility was tied to the branch event instead of the validated revision and its change-impact result.

**Resolution**  
Automatic staging deployment now listens to successful completion of the `CI` workflow, resolves the exact CI-validated SHA, runs AppFactory impact analysis for that commit range, and only builds/deploys when web, API or staging surfaces are affected. Manual deploy remains an intentional full validation path.

**Prevention**  
Deployment workflows must consume a validated immutable revision, not merely observe the same source-control event as CI. Expensive delivery work must also use the repository impact map so no-op changes stay no-op.

**Generalized lesson**  
A deployment workflow running “after a push” is not equivalent to a deployment workflow running “after validation.” Event ordering is part of the release safety model.

**RAIDER impact**  
Strengthens Durable/Non-regressive and Engineering-grade behavior, and applies the RAIDER change-impact rule to deployment rather than only test selection.
