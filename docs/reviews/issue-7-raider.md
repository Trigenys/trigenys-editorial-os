# RAIDER review — Issue #7 Source Registry and Scout

## Reusable

- One `SourceAdapter` contract covers feeds and future source integrations.
- One `PageExtractor` contract covers HTTP, Crawl4AI and later extraction engines.
- URL canonicalization/fingerprinting is shared by all source kinds.
- Source health/backoff is provider-independent.

## Agnostic

- RSSHub output is converted to generic RSS/Atom input.
- Crawl4AI is an optional adapter and never appears in domain contracts.
- Source Registry stores provider configuration as bounded configuration, not SDK objects.
- Scout emits canonical `SourceItem` records only.

## Idempotent

- source/external ID remains unique;
- source/identity key is unique;
- source/content fingerprint remains unique;
- source row locking serializes reconciliation;
- a repeated fetch creates another `SourceFetch`, not another canonical signal.

## Durable / Non-regressive

- Existing source/source-item tables are extended rather than replaced.
- Migration backfills identity keys without requiring PostgreSQL extensions.
- Raw fetches are separated from normalized items.
- Source health/cursor/backoff survive process restarts.
- legacy `SourceItem.raw_content` remains nullable for compatibility.

## Engineering-grade

- timeout and retry policy are explicit;
- retryable vs terminal failures are persisted;
- backoff is bounded;
- retention/redaction rules apply to raw source payloads;
- raw SHA-256 survives raw-content redaction;
- malformed individual URLs are rejected without multiplying signals;
- provenance links every canonical signal to source + fetch;
- deterministic fixtures and a real Atom smoke cover the path.

## Reuse-first

**Adopt:**
- feedparser 6.0.14 for RSS/Atom parsing.

**Adapt:**
- RSSHub as a route/feed adapter.
- Crawl4AI 0.9.4 behind the optional `PageExtractor` boundary.

**Build:**
- source registry;
- health/backoff rules;
- URL normalization;
- identity/content fingerprinting;
- raw-vs-normalized persistence;
- canonical upsert semantics.

Those are Editorial OS product invariants and should not be delegated to a crawler.

## Retroactive

- Existing source records receive safe defaults in migration `0005`.
- Existing source items receive deterministic backfilled identity keys.
- New source adapters do not require core schema changes.
- A second vertical consumes the same registry through `vertical_keys`, with no vertical-name branches.

## Issue #7 Proof of Done mapping

- [x] Same source item ingested twice reconciles to one canonical `SourceItem`.
- [x] Each fetch remains separately attributable through `SourceFetch`.
- [x] Adapter failures are classified retryable/terminal.
- [x] Raw fetch and normalized representation are separate.
- [x] Source/fetch provenance is retained.
- [x] RSS/Atom deterministic fixture covers the end-to-end path.
- [x] Public Atom source smoke covers the real adapter path.
- [x] RSSHub is replaceable.
- [x] Crawl4AI is replaceable and optional.
- [x] Timeout/backoff/source health are durable.
