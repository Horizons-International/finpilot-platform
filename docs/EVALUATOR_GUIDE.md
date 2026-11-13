# FinPilot evaluator guide

This guide is for an independent technical reviewer who has received the FinPilot repository. It is designed to make the first review reproducible and to distinguish implemented code from configuration-dependent integrations and production-readiness claims.

## 1. Review scope

Review this repository as a backend/API platform. The implementation lives under `backend/app/`; FastAPI routes are assembled in `backend/app/main.py`, data models are registered through the model packages, and database changes are managed by Alembic. The root-level `frontend/` and `mobile/` folders are empty placeholders, not runnable client applications.

Use the root README for orientation and [backend/README.md](../backend/README.md) for complete setup commands.

## 2. Before running anything

1. Confirm the Git branch and commit SHA being evaluated.
2. Inspect the tracked-file list for secrets. **The repository tree currently includes `docker/.env` even though .env files are ignored.** Do not publish or reuse its contents. Review it privately, remove it from tracking, replace it with a safe example file and rotate any credentials that may have been committed, including credentials in Git history.
3. Use synthetic data only. Do not connect test runs to production databases or real bank/customer records.
4. Use an isolated local Docker environment and unique passwords/secrets.
5. Record the Docker/Compose and Python versions and the reviewed commit SHA.

## 3. Recommended first run

Follow the exact commands in [backend/README.md](../backend/README.md). The high-level sequence from the repository root is:

```bash
# Configure docker/.env privately first; see backend/README.md.
docker compose -f docker/docker-compose.yml build backend
docker compose -f docker/docker-compose.yml up -d postgres

# Apply schema through the migration history.
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic upgrade head
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic current
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic heads

# Bootstrap a local platform administrator.
docker compose -f docker/docker-compose.yml run --rm backend uv run python -m admin_script.seed_admin

# Start API, workers, proxy and observability.
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

The API is exposed through HAProxy on http://localhost:8000. Check:

- `GET /health` — application liveness.
- `GET /ready` — readiness, including database connectivity.
- `/docs` — Swagger UI.
- `/redoc` — ReDoc.
- `/openapi.json` — generated OpenAPI schema.

Log in through `POST /api/v1/auth/login`, then authorize Swagger with the returned access token. Do not assume that every route accepts the same role or authentication mechanism; inspect its OpenAPI operation and implementation.

## 4. Suggested demonstration sequence

Use synthetic test records and a dedicated local reviewer account.

| Step | Demonstration | What to verify |
|---|---|---|
| 1 | Health/readiness and OpenAPI | API process, database connection, route catalogue |
| 2 | Login and current-user/profile | Token issuance, protected route behavior and identity |
| 3 | Tenant/customer operations | Tenant context and expected role checks |
| 4 | Verification/document flow | Case lifecycle, document/file permissions, provider mode |
| 5 | Compliance/transaction risk | Rules, case records, scoring or monitoring inputs/outputs |
| 6 | Tasks/workflows/SLA | Assignment, status transitions and worker behavior |
| 7 | Reporting/analytics | Query filters, tenant scope and export lifecycle |
| 8 | API keys/integrations/webhooks | Permissions, secret handling and delivery behavior |
| 9 | Sandbox | Synthetic data separation and simulated webhook behavior |
| 10 | Billing/support/customer success/feedback | Lifecycle, tenant access and feature-specific constraints |
| 11 | AI/RAG | Prompt versioning, retrieved context, model/provider and interaction logs |

This is a suggested sequence, not a claim that each integration is configured with a live third-party provider. Mock mode is the default for several providers.

## 5. Inspecting the implementation

Recommended source paths:

- API composition and middleware: `backend/app/main.py`, `backend/app/api/`, `backend/app/middleware/`.
- Configuration and database/session behavior: `backend/app/core/`.
- SQLAlchemy models: `backend/app/models/` and `backend/app/analytics/models/`.
- Business logic: `backend/app/services/` and feature-specific service packages.
- Data access and tenant-scoped query logic: `backend/app/repositories/`.
- Request/response contracts: `backend/app/schemas/`.
- Database evolution: `backend/alembic/versions/`.
- Automated tests: `backend/tests/unit/` and `backend/tests/integration/`.
- Background jobs: `backend/app/jobs/`.

Check implementation and tests together. A route existing in the router list is not enough to establish correct authorization, tenant isolation, transaction behavior or failure handling.

## 6. Run verification

From `backend/`, use a dedicated PostgreSQL test database with pgvector installed. Set both `DATABASE_URL` and `TEST_DATABASE_URL` to the disposable test DSN as described in the backend README.

```bash
uv sync --locked
uv run alembic upgrade head
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest -q
```

For a separate security/performance review, use:

- [Security test plan](../security-testing/SECURITY_TEST_PLAN.md) and [checklist](../security-testing/SECURITY_TEST_CHECKLIST.md).
- [Performance test plan](performance-testing/TEST_PLAN.md) and [performance runner guide](../performance/README.md).
- [Bottleneck register](performance-testing/BOTTLENECK_REGISTER.md).
- [Disaster-recovery procedures](disaster-recovery/README.md) and [recovery record](disaster-recovery/recovery-test-record.md).

Always record the actual command, environment, commit SHA and final result. Do not treat documentation, test scaffolding or workflow definitions as proof of a passing run.

## 7. Review checklist

### Product and API
- [ ] API starts from a clean database using the documented migration process.
- [ ] OpenAPI is generated from the running checkout and protected routes enforce the intended auth and roles.
- [ ] Validation and error responses are understandable and do not leak internal details.
- [ ] The mock-vs-real provider configuration is clear to operators.

### Tenant isolation and authorization
- [ ] Tenant-owned reads, writes, updates, deletes and nested-resource access are scoped to the authenticated tenant.
- [ ] Attempts to access another tenant's IDs fail safely.
- [ ] Cross-tenant/platform operations are restricted to trusted platform-admin context and have auditable reasons.
- [ ] Child rows cannot be attached to parent rows in another tenant where composite ownership constraints are intended.

### Security and privacy
- [ ] No secrets or live customer information are present in repository content or Git history.
- [ ] Production secrets are injected from a secret manager and have a rotation process.
- [ ] HTTPS, database TLS, trusted proxy handling, distributed rate limits and storage access controls match the deployment.
- [ ] Logs avoid credentials, access tokens, document contents and unnecessary sensitive personal data.
- [ ] Security testing has current evidence and findings have owners/remediation status.

### Operations and quality
- [ ] CI checks pass for the exact commit reviewed.
- [ ] Database backups and physical file-storage backups are both covered and restore-tested.
- [ ] Workers, queues/retries and scheduled tasks are monitored.
- [ ] Performance baselines and capacity targets are evidence-based.
- [ ] Deployment rollback and environment isolation have been tested.

## 8. Review outcome record

Record the following in your assessment:

- Repository URL, branch and full commit SHA.
- Runtime environment and dependency versions.
- Setup/migration result.
- Test command, pass/fail/skip counts and captured logs.
- Security findings and severity.
- Tenant-isolation tests performed and outcomes.
- Performance workload, sample size, latency percentiles and infrastructure sizing.
- Backup/restore test result.
- Confirmed limitations, assumptions and recommended next steps.

## 9. Important limitations

Read [Known limitations](KNOWN_LIMITATIONS.md). In particular, this is a backend/API deliverable; mock provider use is expected in an unconfigured local environment; the sandbox does not send webhook requests; billing does not process payments; and the process-local limiter is not a distributed rate-limit solution.
