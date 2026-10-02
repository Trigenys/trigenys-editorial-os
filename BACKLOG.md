# Executable backlog

This file mirrors the GitHub Issues and records the intended dependency order. GitHub Project automation remains the operational board.

## Discovery
- #1 Freeze product contract, risk classes and architecture decisions.

## Foundation
- #2 Introduce FastAPI + PostgreSQL runtime beside the React console. Depends on #1.
- #3 Define editorial domain model, contracts and audit ledger. Depends on #1 and #2.
- #5 Add model gateway, budgets and deterministic model test doubles. Depends on #3.
- #6 Add run correlation, Langfuse tracing and PostHog telemetry boundaries. Depends on #4 and #5.

## Orchestration
- #4 Implement durable workflow state machine and three human gates. Depends on #3.

## Agents
- #7 Implement Source Registry and Scout Agent. Depends on #3, #4 and #6.
- #8 Implement Editorial Intelligence Agent. Depends on #7 and #5.
- #10 Implement Content Agent and versioned vertical-pack contract. Depends on #9 and #5.
- #11 Implement Creative Agent and asset manifest. Depends on #10 and #3.

## Editorial Safety
- #9 Implement Research & Verification Agent with claim/evidence ledger. Depends on #8, #5 and #3.
- #12 Implement Editorial QA Agent and confidence/risk policy. Depends on #9, #10, #11 and #4.

## Integrations
- #13 Implement idempotent Payload CMS publishing adapter. Depends on #12 and #4.
- #14 Implement Publishing & Growth distribution adapters. Depends on #13, #6 and #4.

## Pilot
- #15 Build operator console for queues, evidence, gates, costs and run history. Depends on #4, #12, #13 and #14.
- #35 Deploy Editorial OS staging environment and CI/CD. Required to complete #16.
- #16 Run Trigenys Insight staging vertical end-to-end. Depends on #15 and #35.

## Release
- #17 Validate a second materially different vertical consumer. Depends on #16.
- #18 Security, recovery, load/cost budgets and v0.1 release readiness. Depends on #17, #6, #14 and #13.

## Critical path
#1 → #2 → #3 → #4 → #7 → #8 → #9 → #10 → #11/#12 → #13 → #14 → #15 → #35 → #16 → #17 → #18

## MVP checkpoint
The MVP is considered demonstrated when a real source signal completes source ingestion → topic approval → research/verification → draft → asset → QA → editorial approval → publication approval → Payload staging/publish → distribution preview, with one auditable workflow run and no duplicate side effects on retry.
