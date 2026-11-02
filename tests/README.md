# Test directory orientation

The automated backend suite is under **`backend/tests/`**. The repository-root `tests/` directory is currently a placeholder and does not contain the backend test suite.

Run tests from `backend/` using the uv-locked environment:

```bash
uv sync --locked
uv run pytest -q
```

The integration suite expects PostgreSQL configured through `TEST_DATABASE_URL`; the server must provide pgvector as required by the Alembic history. Use a dedicated disposable database and apply migrations first. Do not use real customer data or a production database.

For focused runs:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
```

See [backend README](../backend/README.md), [development guide](../docs/DevelopmentGuide.md) and [evaluator guide](../docs/EVALUATOR_GUIDE.md).
