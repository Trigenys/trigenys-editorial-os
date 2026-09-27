# RAIDER review — Issue #2 runtime foundation

## Reusable

- The FastAPI runtime contains only platform/runtime concerns.
- No Trigenys Insight, GL, anime or other vertical behavior is introduced.
- Local bootstrap and CI are generic for later domain capabilities.

## Agnostic

- Configuration is environment-driven through the `EDITORIAL_OS_` prefix.
- The frontend and backend remain independently deployable.
- PostgreSQL is reached through SQLAlchemy/psycopg rather than provider-specific cloud APIs.
- Deployment target is still intentionally undecided.

## Idempotent

- `docker compose up -d db` reconciles the local database service.
- Re-running `scripts/bootstrap.py` reuses the virtual environment and existing PostgreSQL volume.
- Alembic upgrade to `head` is convergent.
- CI exercises `upgrade → downgrade → upgrade`.

## Durable / Non-regressive

- The original React/Vite checks remain in CI as a separate web job.
- The backend is added beside, not instead of, the AppFactory frontend baseline.
- The initial migration intentionally creates no domain tables; Issue #3 owns the editorial schema.

## Engineering-grade

- Current stable FastAPI/SQLAlchemy/Alembic/Pydantic Settings lines were checked before selecting version ranges.
- Liveness and database readiness are separate endpoints.
- CI runs lint, strict mypy, tests and real PostgreSQL migration round-trips.
- Secrets/production credentials are not stored in the repository; committed database credentials are local-development-only defaults for the disposable Compose service.

## Reuse-first

Repository reconnaissance found no reusable first-class Trigenys FastAPI service foundation; existing search hits were legacy vendored virtual-environment contents. We therefore **Build** a thin runtime using mature OSS rather than copy legacy application code.

Adopt/Adapt:
- FastAPI — Adopt
- SQLAlchemy 2.0 — Adopt
- Alembic — Adopt
- Pydantic Settings — Adopt
- psycopg 3 — Adopt
- Docker Compose PostgreSQL — Adapt for local development

## Retroactive

- The runtime is additive to the existing AppFactory-generated repository.
- No existing frontend file layout is moved.
- Future services can adopt the backend pattern without requiring a repository reset.

## Issue #2 Proof of Done mapping

- [x] One command path is documented for local web + API development.
- [x] API liveness and readiness endpoints exist.
- [x] PostgreSQL local development configuration exists.
- [x] Migration up/down/up behavior is automated in tests.
- [x] CI validates both runtimes.
- [x] Runtime configuration uses environment variables/settings.
- [x] Bootstrap operations are retry-safe/convergent.
- [x] Existing React build remains part of CI.
