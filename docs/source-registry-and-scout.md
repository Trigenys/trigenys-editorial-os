# Source Registry and Scout

Issue #7 adds deterministic, repeatable source ingestion before editorial intelligence.

## Boundary

The Scout Agent does **not** choose angles, decide truth, draft content or mutate editorial workflow state.

It only turns approved source inputs into normalized, provenance-rich `SourceItem` records.

```text
Source Registry
   │
   ├── RSS / Atom adapter
   ├── RSSHub adapter
   └── manual URL
          │
          ├── HTTP text extractor
          └── Crawl4AI extractor (optional)
   │
   ▼
SourceFetch  ── raw fetch/result/health evidence
   │
   ▼
normalize + canonical URL + fingerprints
   │
   ▼
SourceItem   ── canonical normalized signal
```

## Source Registry

A source stores:

- source kind;
- enabled state;
- trust tier;
- default evidence tier;
- locale;
- eligible vertical keys;
- retention policy;
- raw-content redaction flag;
- adapter-specific configuration;
- fetch interval/timeout/backoff policy;
- cursor;
- health state;
- consecutive failure count;
- next allowed fetch time;
- last success/failure/error kind.

An empty `vertical_keys` list means the source is eligible for every vertical.

## Fetch policy

Default policy:

- 15-minute interval;
- 20-second timeout;
- exponential backoff;
- six-hour maximum backoff;
- pause after eight consecutive failures.

Retryable failures keep the source `DEGRADED` and schedule the next attempt.

Terminal failures, or reaching the failure ceiling, set the source to `PAUSED`.

A forced operator run can intentionally bypass due/backoff/pause checks.

## Raw fetch vs normalized item

`SourceFetch` stores fetch-level provenance:

- source;
- adapter;
- requested URL;
- success/failure;
- retryability and failure class;
- HTTP status/content type;
- timestamps;
- raw payload when retention policy permits;
- SHA-256 of the raw payload;
- bounded error information.

`SourceItem` stores the normalized signal:

- canonical URL;
- source-scoped identity key;
- content fingerprint;
- title;
- normalized body/summary payload;
- locale;
- publication/observation times;
- provenance linking back to the source and fetch.

New Scout ingestion does not copy raw HTML/XML into `SourceItem.raw_content`; that legacy field remains nullable for schema compatibility.

## Idempotency and deduplication

Three source-scoped identities protect ingestion:

1. external source ID when available;
2. deterministic identity key derived from external ID or canonical URL;
3. content fingerprint.

The source row is locked while normalized items are reconciled. Re-fetching the same item updates the existing canonical `SourceItem` while recording a new `SourceFetch`.

Therefore fetch history is append-like, while the canonical source signal does not multiply.

## URL canonicalization

Canonicalization:

- lowercases scheme and host;
- removes URL fragments;
- removes default ports;
- removes trailing slash except root;
- sorts query parameters;
- removes known tracking parameters such as `utm_*`, `fbclid` and `gclid`;
- rejects incomplete/non-HTTP(S) URLs.

## Adapters

### RSS / Atom

`RssAtomAdapter` uses HTTPX and feedparser.

It classifies:

- timeout/network failures as retryable;
- HTTP 429 and 5xx as retryable;
- HTTP 4xx as terminal;
- structurally unusable feeds as terminal parse failures.

### RSSHub

`RSSHubAdapter` only knows how to build the RSSHub endpoint from:

- `base_url`: the RSSHub instance;
- `config.route`: the RSSHub route.

The returned feed still passes through the generic RSS/Atom path. RSSHub-specific shapes never enter domain contracts.

### Manual URL

`ManualUrlAdapter` accepts any `PageExtractor`.

The lightweight default is `HttpPageExtractor`.

### Crawl4AI

`Crawl4AIExtractionAdapter` is optional and loaded lazily.

Install with:

```bash
pip install -e "./backend[crawl]"
```

Crawl4AI is not installed in the default API/CI dependency path because browser-oriented extraction is materially heavier than feed ingestion.

The adapter can also accept an injected crawler factory for deterministic tests.

## Real-source smoke

The integration suite exercises a public GitHub releases Atom feed end-to-end:

```text
https://github.com/fastapi/fastapi/releases.atom
```

It goes through HTTP fetch, feed parsing, normalization, PostgreSQL `SourceFetch`, and canonical `SourceItem` persistence.

Deterministic MockTransport fixtures cover the same path without depending on the network.

## Failure taxonomy

Source failures are explicit:

- `TIMEOUT`;
- `HTTP_RETRYABLE`;
- `HTTP_TERMINAL`;
- `PARSE`;
- `EXTRACTION`;
- `CONFIGURATION`;
- `UNKNOWN`.

Every failure records whether retry is legal.

## Exit strategy

The core depends on `SourceAdapter` and `PageExtractor` protocols, not RSSHub or Crawl4AI types.

Either external project can therefore be removed or replaced without changing Source Registry or SourceItem domain/persistence contracts.
