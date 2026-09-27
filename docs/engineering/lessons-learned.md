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
