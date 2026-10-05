# Cloudflare zero-cost staging

Issue #35 uses Cloudflare as the pre-revenue staging runtime. Issue #46 moves Cloudflare mutations behind AppFactory so the product repository does not own provider credentials.

## Architecture

```text
GitHub Actions (OIDC only)
          ↓
      AppFactory
          ↓
Cloudflare staging Worker
  ├─ Workers Static Assets → React/Vite operator console
  └─ Python Worker / ASGI → canonical FastAPI app
                              ↓
                         Hyperdrive
                              ↓
                         Neon staging
                              ↓
                       Payload staging
```

AppFactory is the Cloudflare control plane. The Editorial OS repository never receives a Cloudflare API token, Cloudflare account ID or database password.

## Cost rule

This path must stay viable on the zero-cost pre-revenue architecture:

- no EC2;
- no NAT Gateway;
- no Cloudflare Containers;
- React/Vite served through Workers Static Assets;
- FastAPI runs as a Python Worker;
- PostgreSQL remains on the existing Neon staging database;
- Hyperdrive is provisioned by AppFactory.

The old AWS staging artifacts remain as a fallback reference only. Do not provision the AWS staging stack for this pilot.

## Ownership and identity

The canonical workflow is:

```text
.github/workflows/appfactory-infrastructure.yml
```

It authenticates to AppFactory with a short-lived GitHub Actions OIDC token using audience `appfactory-api`.

For `environment: staging`, AppFactory owns deterministic resources:

```text
Worker      trigenys-editorial-os-staging-api
Hyperdrive  trigenys-editorial-os-staging
DB profile  trigenys-editorial-os-staging
```

The database profile is AppFactory-owned. Repository requests never contain PostgreSQL host, user or password fields.

## Release sequence

The workflow deliberately runs three retry-safe mutations:

```text
1. bootstrap/reconcile managed staging Worker
2. provision/reconcile staging Hyperdrive
3. reconcile Worker again with:
   - Hyperdrive binding
   - Alembic migration gate
   - database readiness probe
```

The first Worker pass creates the managed ownership marker. Hyperdrive refuses to adopt an unrelated Worker. The second Worker pass injects the exact Hyperdrive identity into the deployment and blocks release if database readiness fails.

## Packaging

AppFactory permits only its reviewed runtime-only Python Worker recipe:

```text
build:
bash scripts/package_worker.sh dry-run wrangler.production.toml ../worker-dist-production

deploy:
bash scripts/package_worker.sh deploy wrangler.production.toml
```

Cloudflare Builds runs from `/backend`. The packaging script builds the real Vite console, copies the canonical `editorial_os_api` package into the isolated Python Worker context, installs the minimal compatible Worker runtime dependencies, then invokes Pywrangler.

`backend/wrangler.production.toml` owns the staging Worker/static-assets configuration. AppFactory appends the managed Hyperdrive binding to an ephemeral copy during release; the database UUID is not committed.

## Database migration

AppFactory injects the centrally managed database URL only into the build-time Alembic gate using:

```text
TRIGENYS_EDITORIAL_OS_DATABASE_URL
```

`backend/migrations/env.py` accepts that release-only variable while the runtime Worker itself connects through the `HYPERDRIVE` binding.

## Payload

Payload staging remains a separate acceptance dependency. Production Payload credentials must never be reused.

When staging credentials are available, expose them through AppFactory-managed runtime secrets, not repository secrets. The Worker adapter will remain responsible for mapping provider-managed names into the canonical application settings.

## CI proof

The `cloudflare-spike` job executes the same `backend/scripts/package_worker.sh` dry-run recipe that AppFactory will use in Cloudflare Builds. A toy Worker is not considered proof.

## Acceptance before closing #35

Do not mark #35 complete until the live AppFactory-managed Worker proves:

- `/health` returns `environment=staging` and `deployment=cloudflare-worker`;
- `/health/ready` reaches Neon through the AppFactory-managed Hyperdrive binding;
- Alembic is at head;
- the operator console loads through Workers Static Assets and calls the same-origin API;
- gate mutations remain retry-safe;
- repeated infrastructure reconciliation is idempotent;
- staging Payload connectivity is proven without production credentials;
- no AWS compute resource was created.
