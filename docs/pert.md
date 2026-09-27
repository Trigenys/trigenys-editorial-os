# PERT / dependency map

The backlog is organized to minimize rework rather than maximize parallel issue count.

```text
Product contract / ADRs
        │
        ├──────────────┐
        ▼              ▼
Domain + data      Reuse/security
contracts          reconnaissance
        │              │
        └──────┬───────┘
               ▼
      Runtime foundation
               │
               ▼
   Orchestrator + gate engine
          │         │
          │         └──────────────► Observability/cost controls
          ▼
     Scout ingestion
          │
          ▼
 Editorial Intelligence
          │
          ▼
 Research & Verification
          │
          ├──────────────► Creative
          ▼
        Content
          │
          └──────┬────────► Editorial QA
                 │
                 ▼
       Publishing integrations
                 │
                 ▼
          Operator console
                 │
                 ▼
        Insight staging pilot
                 │
                 ▼
      Second-consumer validation
                 │
                 ▼
              Release
```

## Critical path

1. contracts/data;
2. runtime;
3. orchestrator/gates;
4. ingestion;
5. editorial intelligence;
6. verification;
7. content;
8. QA;
9. publishing;
10. operator console;
11. real pilot;
12. second-consumer validation.

Creative generation and some growth integrations can progress in parallel after the core contracts stabilize.

## Exit principle

No downstream issue may silently compensate for a broken upstream contract. If an upstream contract changes, update the contract/version and affected tests explicitly.
