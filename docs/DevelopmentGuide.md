# Development guide

## Environment

- Python 3.12+.
- uv and the committed lockfile.
- Docker Compose v2 for the recommended PostgreSQL/pgvector environment.
- PostgreSQL with pgvector for host-run API and integration tests.

The active backend is under `backend/`. Commands below that reference `uv` and Alembic should be run from that directory unless stated otherwise. The top-level [README](../README.md) and [backend setup guide](../backend/README.md) explain the complete Docker-first setup.

## First-time host environment setup

```bash
cd backend
uv sync --locked
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env`. Edit .env with a dedicated local PostgreSQL DSN, unique SECRET_KEY and safe bootstrap admin credentials. Never commit .env.

## Database and local API

Ensure PostgreSQL server has the vector extension and the target database is disposable/local. From `backend/`:

```bash
uv run alembic upgrade head
uv run python -m admin_script.seed_admin
uv run uvicorn app.main:app --reload
```

Use Docker Compose if installing pgvector locally is not practical.

## Tests and static checks

Set DATABASE_URL and TEST_DATABASE_URL to the dedicated test database. From `backend/`:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run pytest -q
uv run ruff check .
uv run black --check .
uv run mypy .
```

The CI workflow installs locked dependencies, applies migrations and runs all the quality checks/tests. Check current commit status on GitHub.

## Making a change

1. Create a focused feature branch.
2. Inspect existing API, schema, model, repository, service and test patterns.
3. Define tenant ownership and authorization before implementing the happy path.
4. Add model/schema/repository/service/API changes with migration where needed.
5. Add unit and DB integration tests for success and negative/security paths.
6. Update feature docs and configuration templates.
7. Run migrations, tests, Ruff, Black and MyPy.
8. Inspect the full diff, remove generated files/secrets, commit and open a PR.
9. Resolve CI findings before merge.

## Pre-commit note

The checked-in pre-commit configuration pins Ruff, Black and MyPy hooks. It also contains a local pytest executable path specific to a Windows virtual environment. On another platform, review or adapt that local hook rather than assuming the same path exists.

## Useful operational resources

See [deployment](../deploy/README.md), [security testing](../security-testing/README.md), [performance](../performance/README.md) and [disaster recovery](disaster-recovery/README.md).
