# Editorial OS staging deployment

Issue #35 provides the isolated staging runtime required before the real Trigenys Insight pilot in #16.

## Architecture

The staging runtime follows the same deployment shape already used for Trigenys AWS workloads:

```text
GitHub Actions
  ├─ build API + web images
  ├─ push immutable images to GHCR
  └─ OIDC → AWS → SSM Run Command
                         ↓
                   EC2 staging host
                    ├─ Nginx web
                    └─ FastAPI API
                         ↓
                  PostgreSQL staging
                         ↓
                    Payload staging
```

The operator console and API are separate containers. Nginx is the application entry point and proxies `/api/` to the API container over a private Docker network.

The EC2 security group has **no inbound rules**. There is no SSH port and no publicly exposed operator console. Human access is through AWS Systems Manager port forwarding.

## Database

The runtime uses a dedicated PostgreSQL database and role named `editorial_os_staging`. Its connection string is a secret and must never be committed.

The application expects SQLAlchemy + psycopg. The host secret loader automatically converts a standard `postgresql://...` URL into `postgresql+psycopg://...`.

## One-time GitHub environment setup

Create or reuse the GitHub environment named `staging` and set these non-secret variables:

```text
AWS_REGION=eu-west-3
AWS_CLOUDFORMATION_ROLE_ARN=<existing Trigenys CloudFormation OIDC role ARN>
AWS_DEPLOY_ROLE_ARN=<existing Trigenys deployment OIDC role ARN>
STAGING_STACK_NAME=trigenys-editorial-os-staging
STAGING_DEPLOY_ENABLED=false
```

The workflows deliberately reuse the existing Trigenys OIDC split: infrastructure mutations use the CloudFormation role, while deployments use the deployment role.

Keep `STAGING_DEPLOY_ENABLED=false` until the host and runtime parameters are ready. Manual deploys remain available. After the first successful deployment, set it to `true` to deploy every green merge to `main`.

## Provision the host

Run:

```text
Actions → Provision staging infrastructure → Run workflow
```

The workflow applies `infra/aws/staging.yml`, which creates:

- one small Ubuntu 24.04 EC2 instance (default `t3.micro`);
- a 20 GB encrypted gp3 root volume;
- an instance profile with SSM core permissions;
- read-only access to the Editorial OS staging Parameter Store prefix;
- a security group with outbound access only.

The host bootstrap installs Docker, Docker Compose, Git, AWS CLI, curl and jq.

No public SSH key or inbound application port is created.

## Runtime secrets

Create these `SecureString` values in AWS Systems Manager Parameter Store:

```text
/trigenys/editorial-os/staging/database-url
/trigenys/editorial-os/staging/payload-base-url
/trigenys/editorial-os/staging/payload-api-token
/trigenys/editorial-os/staging/ghcr-token
```

Optional parameters:

```text
/trigenys/editorial-os/staging/payload-collection
/trigenys/editorial-os/staging/payload-auth-mode
/trigenys/editorial-os/staging/payload-auth-collection
/trigenys/editorial-os/staging/ghcr-user
```

Defaults:

```text
payload-collection=posts
payload-auth-mode=bearer
payload-auth-collection=users
ghcr-user=EagleFox31
```

The GHCR token needs package-read permission only on the staging host. Application credentials stay server-side. Production Payload credentials must not be copied into this prefix.

The host renders a mode-0600 `.env`; neither the GitHub workflow nor the browser receives database or Payload credentials.

## Deploy sequence

`.github/workflows/deploy-staging.yml` performs:

```text
build API/web
→ push commit-SHA images to GHCR
→ OIDC into AWS
→ resolve EC2 from the CloudFormation stack
→ SSM command
→ fetch runtime secrets from Parameter Store
→ pull immutable GHCR images
→ alembic upgrade head
→ seed approved Insight sources
→ read-only Payload connectivity check
→ start API + web
→ smoke /health/web
→ smoke /health/api
→ smoke /health/ready
```

The deployment is retry-safe. A second deployment of the same commit does not create a new schema migration, a duplicate pilot source, or a CMS document.

The API health response must report:

```json
{
  "status": "ok",
  "environment": "staging",
  "deployment": "staging"
}
```

The operator console also renders a visible `staging` badge.

## Private operator access

Resolve the instance id from the CloudFormation stack, then use Session Manager port forwarding:

```bash
aws ssm start-session \
  --region eu-west-3 \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8080"],"localPortNumber":["8080"]}'
```

Open:

```text
http://127.0.0.1:8080
```

This gives browser access to the console without opening port 8080 on the Internet.

## Rollback

Every successful deployment keeps the prior API/web image references in `.release.previous.env`.

Run:

```text
Actions → Deploy staging → Run workflow → action = rollback
```

Rollback restores the previous application images and reruns smoke tests.

Schema downgrades are intentionally **not** automatic. Alembic migrations are forward-only in this deployment path. If a migration proves incompatible, fix forward or restore the staging database through the database provider's recovery tooling rather than silently rewriting schema history.

## Host-local diagnostics

Via an SSM shell:

```bash
cd /opt/trigenys/editorial-os/staging
BASE_URL=http://127.0.0.1:8080 ./smoke.sh
docker compose -f compose.staging.yml ps
docker compose -f compose.staging.yml logs --tail=200 api
```

Never print or `cat` the runtime `.env`.

## Gate to #16

Issue #35 is complete only after the real host exists and one deployment passes:

- Alembic at head;
- web health;
- API staging identity;
- database readiness;
- idempotent source seeding;
- read-only Payload staging connectivity;
- repeat deployment of the same revision;
- manual rollback smoke test.

Only then should #16 start scenario 1 of the ten real Trigenys Insight staging runs.
