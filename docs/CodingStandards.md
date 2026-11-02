# Coding standards

## Runtime and tooling

The backend targets Python 3.12 or newer. Dependency versions are managed with `backend/pyproject.toml` and the committed `backend/uv.lock`. Install reproducibly with `uv sync --locked`.

Configured quality tools:
- Ruff linting and import checks; line length 88.
- Black formatting; line length 88.
- MyPy static analysis; Python 3.12 target.
- pytest for unit and PostgreSQL integration tests.
- pre-commit hooks defined in `backend/.pre-commit-config.yaml`.

Run from `backend/`:

```bash
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest -q
```

## Layering

Follow the established package layout:
- API routers validate HTTP input, resolve auth/context and translate service results to HTTP.
- Services own business rules, access decisions, orchestration and transaction boundaries.
- Repositories own database queries and persistence.
- Models represent persisted domain state.
- Schemas represent validated API contracts.
- Shared utilities contain genuinely reusable, business-agnostic helpers.

Avoid direct ORM query logic in API handlers and avoid duplicating authorization rules across routers.

## Typing and errors

Use explicit parameter and return annotations, especially on repositories/services and public helpers. Prefer narrow protocols and concrete return types over Any. Do not hide type errors with broad ignores without a documented reason.

Raise domain-appropriate exceptions and let the existing API error-handling layer convert them into safe HTTP responses. Do not swallow unexpected exceptions or return success-shaped empty data after an unexpected failure.

## Database discipline

Use the injected SQLAlchemy session and repository conventions. Repositories should generally flush/execute but should not independently commit transactions owned by the service/request boundary. Avoid hidden commits that make multi-step operations partially durable.

Create an Alembic revision for schema changes. Review its upgrade and downgrade functions and ensure it handles existing rows, constraints, indexes, defaults and tenant ownership correctly.

## Security and tenancy

- Treat IDs from clients as untrusted.
- Always apply tenant scope to tenant-owned rows.
- Add role/permission checks at the correct service/API boundary.
- Review nested resources and mutation endpoints, not only list endpoints.
- Use explicit, narrowly scoped and reasoned tenant-filter bypasses only for trusted platform operations.
- Never log passwords, bearer tokens, API key secrets, encryption material or raw sensitive document content.
- Keep example data synthetic and secrets out of Git.

## Tests

Add unit tests for deterministic schema/business logic and PostgreSQL integration tests for DB-backed behavior. Include normal, invalid, conflict, unauthorized and cross-tenant cases. Clean up only records/files created by the test. Avoid deleting all rows in shared test schemas.

## Pull requests

Keep changes cohesive. Include migration and test changes with feature code. Update the relevant docs and note configuration requirements. Run migrations and quality checks locally before requesting review; then inspect CI for the exact commit.
