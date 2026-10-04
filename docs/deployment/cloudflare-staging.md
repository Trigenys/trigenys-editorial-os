# Cloudflare zero-cost staging spike

Issue #44 tests whether Editorial OS can satisfy issue #35 without an always-on EC2 host.

## Target architecture

```text
Cloudflare Worker
  ├─ Workers Static Assets → React/Vite operator console
  └─ Python Worker / ASGI → canonical FastAPI app
                              ↓
                         Hyperdrive
                              ↓
                         Neon staging
                              ↓
                       Payload staging
```

The application domain and FastAPI routes remain canonical. Cloudflare is a transport/runtime adapter, not a fork of the product.

## Cost rule

The spike must not require Cloudflare Containers or an always-on AWS resource. Static assets use Workers Static Assets. Dynamic API traffic stays within the Workers Free plan during the pilot. Hyperdrive is available on the Free plan.

AWS remains a fallback deployment target only. Do not provision the EC2 staging stack while this spike is active.

## CI proof

The `cloudflare-spike` CI job:

1. builds the real Vite frontend;
2. copies the real `editorial_os_api` package into an isolated Worker build context;
3. installs only the runtime dependencies needed by the currently exposed FastAPI surface;
4. runs a Pywrangler dry-run bundle against the current Python Workers runtime.

The CI Hyperdrive ID is a syntactically valid non-production placeholder and is never used for a live connection.

## Live staging configuration

A live staging deploy must use a real Hyperdrive configuration connected only to the Neon staging database.

Cloudflare binding:

```text
HYPERDRIVE=<staging Hyperdrive configuration>
```

Runtime secrets/vars:

```text
EDITORIAL_OS_PAYLOAD_ENABLED=true
EDITORIAL_OS_PAYLOAD_BASE_URL=<Payload staging URL>
EDITORIAL_OS_PAYLOAD_API_TOKEN=<secret>
```

Optional:

```text
EDITORIAL_OS_PAYLOAD_COLLECTION=posts
EDITORIAL_OS_PAYLOAD_AUTH_MODE=bearer
EDITORIAL_OS_PAYLOAD_AUTH_COLLECTION=users
```

No production Payload credential belongs in this environment.

## Routing

Static assets bypass Python compute. Worker-first routes are limited to:

- `/api/*`
- `/health` and `/health/*`
- FastAPI docs/OpenAPI routes

All other routes use SPA static-asset handling.

## Runtime compatibility notes

Cloudflare Python Workers execute in Pyodide. FastAPI is supported through Cloudflare's ASGI adapter. Hyperdrive supports Python Workers and PostgreSQL drivers including psycopg. Cloudflare documents synchronous SQLAlchemy ORM support; async SQLAlchemy is not currently supported because greenlet is unavailable.

The Worker therefore keeps the existing synchronous SQLAlchemy path for this spike. A live load test is still required before #35 can close.

Telemetry SDKs are lazy-loaded so disabled Langfuse/PostHog integrations do not become mandatory Worker dependencies.

## Acceptance before replacing AWS

Do not mark #35 complete until the live Worker proves:

- `/health` returns `environment=staging` and `deployment=cloudflare-worker`;
- `/health/ready` reaches Neon through Hyperdrive;
- the operator console loads from static assets and calls the same-origin API;
- gate mutations remain retry-safe;
- staging Payload connectivity is read-only until publish-gate testing;
- no production credential is present;
- a repeated deployment is idempotent.
