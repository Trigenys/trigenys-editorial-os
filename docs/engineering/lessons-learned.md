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
