# Editorial OS API

FastAPI + PostgreSQL runtime introduced by Issue #2.

## Runtime

- Python 3.13
- FastAPI
- SQLAlchemy 2.0
- psycopg 3
- Alembic
- Pydantic Settings

## Local commands

From the repository root, bootstrap dependencies and PostgreSQL with:

```bash
python scripts/bootstrap.py
```

Then start the web console and API together:

```bash
python scripts/dev.py
```

Endpoints:

- Web console: http://127.0.0.1:5173
- API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Liveness: http://127.0.0.1:8000/health
- Readiness: http://127.0.0.1:8000/health/ready

## API-only commands

Activate `.venv`, then:

```bash
cd backend
python -m uvicorn editorial_os_api.main:app --reload
python -m pytest
python -m ruff check src tests migrations
python -m mypy src tests
python -m alembic upgrade head
```

The API uses environment configuration prefixed with `EDITORIAL_OS_`.
Never commit production credentials.
