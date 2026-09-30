# Issue #13 — RAIDER review

## Reusable
The publishing service speaks a small provider-neutral `CMSAdapter` contract. Article mapping, asset mapping, idempotency and Gate C policy remain in core; Payload-specific HTTP details stay in the adapter.

## Agnostic
The core never imports Payload-specific fields or endpoints. A second CMS can implement the same `upsert_draft` and `publish` boundary without changing workflow policy.

## Idempotent
The publication key is deterministic for provider + target + exact draft version. The database uniqueness constraint prevents duplicate owned publication rows. CMS draft creation is an upsert and carries both an owner key and idempotency key so a retry can reconcile an existing remote draft.

Final publication is separate from draft creation. Once a publication receipt is stored as `PUBLISHED`, replay advances workflow state if needed without issuing the remote publish call again.

## Durable / non-regressive
No existing domain table contract changes are required. The existing `Publication` model already stores provider, target, external ID, owner key, idempotency key, status and receipt. Existing workflow transitions remain authoritative.

## Engineering-grade
- Gate C is enforced against the exact draft ID and version.
- Retryable and terminal provider errors are distinct.
- Remote failures are persisted and audited.
- Payload transport maps 5xx/408/409/425/429 to retryable failures.
- Locale, canonical draft metadata and assets cross the adapter boundary explicitly.
- Provider credentials stay in environment-backed settings.

## Retroactive
Existing workflow runs and drafts need no destructive migration. A publication row is created only when the publishing service is invoked.

## Failure memory
The main failure mode is a remote mutation succeeding while the local process fails before persisting its receipt. The design mitigates this by preserving a stable owner key and provider idempotency key, allowing the adapter to reconcile an owned Payload draft on retry. A future CMS adapter must provide equivalent reconciliation semantics.

## Proof-of-Done mapping
- Retry creates no duplicate article: `test_retrying_same_cms_draft_creates_no_duplicate_and_maps_locale_assets`.
- Payload outage recoverable: `test_payload_outage_leaves_retryable_publication_and_retry_recovers`.
- Gate C required: `test_final_publish_is_blocked_without_gate_c` and `test_gate_c_exact_draft_version_is_required`.
- CMS IDs stored: publication external ID and provider receipt assertions.
- Second CMS supported: provider-neutral contracts and fixture adapter.
- Draft → approve → publish lifecycle: `test_draft_approve_publish_lifecycle_is_idempotent`.
