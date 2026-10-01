# Trigenys Insight staging pilot

Issue #16 validates Trigenys Editorial OS against the real Trigenys Insight consumer without allowing an automated production publish.

## Frozen pilot contract

- Vertical: `trigenys-insight@2026.10-pilot.1`
- Pilot id: `insight-e2e-2026-10`
- Publication target: Payload staging only
- Representative run count: 10
- Mandatory human gates: A (topic), B (editorial), C (publish)
- Material factual claims must remain traceable to stored claim/evidence records.
- A retry must reconcile to the owned Payload item rather than create another CMS document.

The ten scenarios are code-owned in `editorial_os_api.pilot.insight.PILOT_SCENARIOS`. They cover digital infrastructure, QR/consumer technology, AI skills, startup financing, local e-commerce, cybersecurity, cloud architecture, offline/2G constraints, gaming/digital work and mobile-economy data literacy.

## Approved source registry

The pilot starts from a deliberately small allow-list: MINPOSTEL, ART Cameroon, INS Cameroon, World Bank Cameroon, IFC Africa and GSMA. The seed operation is idempotent and tags every row with the pilot id and stable source key.

After the backend environment is bootstrapped:

```bash
python scripts/insight_pilot.py seed-sources
```

Seeding does not crawl or publish anything. Individual URLs still pass through the Scout adapters and retain normal provenance.

## Staging-only environment

Use a dedicated database and Payload staging project. Provider credentials stay server-side. Do not put API keys or Payload receipts into browser-visible workflow context.

Expected runtime settings include:

```text
EDITORIAL_OS_ENVIRONMENT=production
EDITORIAL_OS_DATABASE_URL=...
EDITORIAL_OS_PAYLOAD_ENABLED=true
EDITORIAL_OS_PAYLOAD_BASE_URL=...
EDITORIAL_OS_PAYLOAD_API_TOKEN=...
EDITORIAL_OS_PAYLOAD_COLLECTION=posts
```

The Payload account must only have the permissions needed for the staging collection. Production credentials are explicitly out of scope for this pilot.

## Execution record for each scenario

For each of the ten scenarios, retain these identifiers in the pilot worksheet or issue comment:

- scenario key
- workflow run id
- source item ids
- topic candidate id/version + Gate A actor/time/outcome
- research brief id and claim/evidence counts
- draft id/version
- asset manifest id/version
- QA review id/outcome/defect count
- Gate B actor/time/outcome
- Payload publication id + external staging id
- Gate C actor/time/outcome
- retry/resume events, if any
- measured duration, tokens, model cost and factual defects

A rejected or revision-requested attempt is valid pilot evidence, but the scenario only counts as completed after a later run reaches a staging publication state without bypassing the configured gates.

## Batch report

Once run ids are known:

```bash
python scripts/insight_pilot.py report \
  --run-id <run-1> \
  --run-id <run-2> \
  --run-id <run-3>
```

Repeat `--run-id` through all ten runs. The report emits human gate touches, retries/failures, duration, model calls/tokens/cost, factual-defect counts and CMS external ids. The batch fails the duplicate-safety acceptance criterion if any external CMS id is reused across distinct runs.

## Exit criteria

Do not close #16 until all ten real staging scenarios have execution evidence. CI fixtures prove the pilot configuration and metric machinery; they do **not** substitute for the real staging run. Any defect found during the pilot must become a tracked issue, regression test or guardrail before the pilot is called complete.
