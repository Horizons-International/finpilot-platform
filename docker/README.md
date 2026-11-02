# Docker development environment

The canonical Docker setup is `docker/docker-compose.yml`, run from the repository root:

```bash
docker compose -f docker/docker-compose.yml build backend
docker compose -f docker/docker-compose.yml up -d postgres
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic upgrade head
docker compose -f docker/docker-compose.yml run --rm backend uv run python -m admin_script.seed_admin
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

The Compose stack uses:
- `docker/Dockerfile` to build the Python backend image.
- `pgvector/pgvector:pg17` for PostgreSQL with the server extension required by the migrations.
- Three API containers behind HAProxy (the local API endpoint is http://localhost:8000).
- SLA, analytics, report export and webhook delivery worker containers.
- pgAdmin, Prometheus and Blackbox Exporter for local administration/observability.

The Compose file reads `docker/.env`. The current repository tracks a file at that path even though environment files should not be committed. Inspect it privately; use local-only credentials and replace/remove tracked secrets before sharing. See [backend setup](../backend/README.md).

PostgreSQL is published to host loopback port 5433; containers use service hostname `postgres:5432`. Uploaded files persist in the `finpilot_storage` volume. `docker compose down` preserves named volumes; `docker compose down -v` deletes them.

Other compose files are specialized environments:
- `docker-compose.sandbox.yml`: separate sandbox API process; requires a separately prepared sandbox database as described in [sandbox API docs](../docs/sandbox-api.md).
- `docker-compose.security-test.yml`: isolated security testing support.
- `docker-compose.dr-test.yml`: disaster-recovery restore/test topology.

The separate release Compose file is under `deploy/compose/`; it does not provision PostgreSQL. See [deployment docs](../deploy/README.md).
