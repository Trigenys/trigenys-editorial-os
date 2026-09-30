# Issue #14 — RAIDER review

## Reusable
Distribution is split into provider-neutral contracts, deterministic channel-copy generation, delivery adapters, optional peripheral hooks and performance ingestion. The core service does not know Postiz or n8n HTTP details.

## Agnostic
- `DistributionAdapter` owns social-provider delivery.
- `PeripheralWorkflowAdapter` owns optional side-effect workflows.
- `PerformanceEvent` is provider-neutral; the PostHog parser only normalizes inbound PostHog payloads.
- Remotion remains disabled by default and can later sit behind an asset/video adapter instead of entering core workflow logic.

## Idempotent
A distribution job is deterministic per provider + publication + channel + integration. Replaying an accepted `SCHEDULED` or `POSTED` job returns the stored job without another remote mutation.

Before a remote social mutation, the job moves to `DISPATCHING`. Ambiguous transport/provider outcomes stay in that state and require reconciliation; automatic retry is blocked so an uncertain request cannot silently double-post. Explicitly retryable pre-delivery failures move to `FAILED_RETRYABLE`.

Performance ingestion uses `workflow_run_id + event_key` uniqueness so the same PostHog event converges to one snapshot.

## Durable / non-regressive
The existing publication and workflow state machines remain authoritative. A failed social channel never changes the canonical `Publication.status`. The only schema extension is additive performance attribution:
- direct topic candidate reference,
- provider,
- stable event key.

Existing snapshots remain valid through nullable/defaulted migration fields.

## Engineering-grade
- Preview generation is local and cannot post.
- Final delivery is separately audited.
- Provider name must match the owned distribution job.
- Canonical publication must already be `PUBLISHED`.
- Ambiguous remote mutations fail closed pending reconciliation.
- PostHog references are validated so publication/job/run IDs cannot be cross-wired.
- Postiz, n8n and Remotion are off by default.
- Secrets are environment-backed and never passed to browser code.

## Retroactive
Existing published articles can create distribution previews without changing their canonical record. Legacy performance rows migrate without destructive reset.

## Reuse-first reconnaissance
Postiz is used rather than rebuilding a multi-network publisher. Its public API exposes a single posts endpoint, connected integrations and analytics. n8n remains a generic webhook boundary for peripheral automations. Existing PostHog telemetry infrastructure is reused for product analytics while inbound content-performance events are normalized into the editorial domain.

Reference: https://docs.postiz.com/public-api/introduction

## Failure memory
Remote social mutations have an unavoidable ambiguity window: the provider may accept a request while the client loses the response. Treating every timeout as an ordinary retry can double-post. The distribution state machine therefore distinguishes safe retry from `DISPATCHING`/reconciliation-required outcomes.

## Proof-of-Done mapping
- Preview without posting: `test_preview_generates_channel_copy_without_posting`.
- Separate audit of final social delivery: `test_successful_distribution_is_audited_and_retry_does_not_double_post`.
- No duplicate accepted job on replay: same test plus persisted idempotency key.
- Channel failure leaves article intact: `test_retryable_channel_failure_does_not_roll_back_article`.
- Ambiguous outcome cannot auto-retry: `test_ambiguous_delivery_requires_reconciliation_before_retry`.
- Performance maps to article/topic/run: `test_posthog_performance_maps_to_article_topic_run_and_is_idempotent`.
- Postiz request contract: `test_postiz_adapter_uses_public_posts_contract_and_stable_headers`.
- Optional integrations disabled by default: `test_distribution_integrations_are_off_by_default`.
