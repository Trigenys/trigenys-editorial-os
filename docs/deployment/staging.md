# Editorial OS staging deployment

Issue #35 provides the infrastructure boundary required before the real Trigenys Insight pilot in #16.

## Architecture

The staging runtime uses two immutable containers on one SSM-managed host:

- `editorial-os-web`: Nginx + the built React operator console.
- `editorial-os-api`: FastAPI + Alembic + the pilot utilities.

Nginx is the only public application entry point. Requests under `/api/` are proxied to the private API container. PostgreSQL is external and reached only by the API/migration containers.

The deployment workflow builds both images, stores them in ECR under immutable commit-SHA tags, runs Alembic before the new application revision, seeds the approved Insight source set idempotently, verifies Payload staging with a read-only request, starts the containers, then runs health/readiness smoke tests.

## Database

The staging database is a dedicated PostgreSQL database and role named `editorial_os_staging`. Its connection string is a runtime secret and must never be committed.

The runtime expects a SQLAlchemy psycopg URL. A standard Neon `postgresql://...` URL is normalized to `postgresql+psycopg://...` by the host bootstrap script.

## One-time AWS host contract

The target EC2 host must have:

- Docker Engine and the Docker Compose plugin;
- AWS CLI v2;
- Git;
- SSM Agent;
- an instance profile that can read the staging SSM parameter prefix and pull the two ECR repositories.

The GitHub `staging` environment needs these non-secret variables:

```text
AWS_REGION=eu-west-3
AWS_ROLE_ARN=<GitHub-OIDC deploy role ARN>
STAGING_EC2_INSTANCE_ID=<SSM managed instance id>
STAGING_BASE_URL=<optional externally reachable URL>
```

The GitHub OIDC role needs only the deployment actions: ECR repository/read-write operations, `sts:GetCallerIdentity`, and SSM `SendCommand` / `GetCommandInvocation` against the staging instance. It does not receive application credentials.

## Runtime secrets

Create these values in AWS Systems Manager Parameter Store as `SecureString` values under:

```text
/trigenys/editorial-os/staging/database-url
/trigenys/editorial-os/staging/payload-base-url
/trigenys/editorial-os/staging/payload-api-token
```

Optional non-default values:

```text
/trigenys/editorial-os/staging/payload-collection
/trigenys/editorial-os/staging/payload-auth-mode
/trigenys/editorial-os/staging/payload-auth-collection
```

`payload-auth-mode` is either `bearer` or `api_key`. Production Payload credentials must not be used here.

The host script writes a mode-0600 `.env` file. Secret values are never passed through the browser, committed files, Docker build arguments, or GitHub workflow output.

## Deployment

Every push to `main` triggers `.github/workflows/deploy-staging.yml` after the environment has been configured. Manual `workflow_dispatch` can also deploy.

The server-side sequence is:

```text
ECR login
→ refresh runtime secrets from SSM
→ pull immutable images
→ alembic upgrade head
→ seed approved Insight sources
→ read-only Payload staging connectivity check
→ start API + web
→ smoke /health/web
→ smoke /health/api
→ smoke /health/ready
```

The API health payload must identify itself as both `environment=staging` and `deployment=staging`. The web console displays a visible staging badge.

## Idempotency

Redeploying the same commit is safe:

- ECR images are content-addressed by commit SHA.
- Alembic `upgrade head` is idempotent once the database is current.
- Insight source seeding reconciles by stable pilot source keys.
- Containers are replaced in place with `docker compose up -d --remove-orphans`.
- Payload verification is GET-only; no CMS content is created by deployment.

## Rollback

The deployment host retains the previous API/web image references in `.release.previous.env`.

Use **Deploy staging → Run workflow → action: rollback** to restore those images. The rollback smoke test must pass before the action succeeds.

Database migrations are forward-only: rollback does not run `alembic downgrade`. If a migration is not backward-compatible, fix forward or restore the staging database from the database provider's recovery mechanism rather than silently mutating schema history.

## Host-local checks

From `/opt/trigenys/editorial-os/staging`:

```bash
BASE_URL=http://127.0.0.1:8080 ./smoke.sh
docker compose -f compose.staging.yml ps
docker compose -f compose.staging.yml logs --tail=200 api
```

No command should print `.env` or Parameter Store values.

## Gate to #16

Issue #35 is complete only when a real deploy reaches staging and the three smoke checks plus the Payload read-only connectivity check pass. After that, #16 can execute scenario 1 through the Operator Console and continue through the ten representative real staging runs.
