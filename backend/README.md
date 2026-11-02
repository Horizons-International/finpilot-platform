# FinPilot Backend

This directory contains the canonical FinPilot application: a Python 3.12+ FastAPI service backed by PostgreSQL. The backend implements tenant-aware business APIs for customer onboarding, identity verification, AML/compliance, operational workflows, reporting, analytics, integrations, billing foundations, support and AI-assisted workflows.

This guide is the authoritative local setup reference for reviewers and developers. The root [README](../README.md) provides the product overview; the [evaluator guide](../docs/EVALUATOR_GUIDE.md) provides a suggested review sequence.

## What is included

- JWT authentication and refresh, user/profile/invitation management, authorization and session controls.
- Tenant and organization management, customers, contacts, addresses and customer history.
- Onboarding and identity verification cases, reviews, assignments and document types.
- File storage, customer documents, document review, OCR and extraction integrations.
- AML rules, transaction monitoring, risk scoring/predictions, investigation and compliance cases.
- Task management, assignment rules, workflow execution, SLA monitoring and notifications.
- Customer/compliance/operations/executive/product analytics and reporting exports.
- API keys, integration management, webhooks, developer portal and isolated synthetic sandbox.
- Billing plans, subscriptions and invoice records.
- Customer success, support tickets, feedback and product roadmap workflows.
- AI prompts, interaction logging, knowledge documents, retrieval and assistant endpoints.

Use the running OpenAPI interface for the route inventory and exact request/response schemas. Provider settings default to mock implementations for local evaluation; this does not mean external production integrations are configured.

## Requirements

- Python 3.12 or newer.
- uv.
- Docker with Docker Compose v2 for the recommended setup.
- PostgreSQL with the pgvector extension. The supplied Docker Compose service uses the pgvector PostgreSQL 17 image.
- Git.

## Recommended setup: Docker Compose

Run commands from the repository root unless the command explicitly says otherwise.

### 1. Prepare a private local environment file

The Compose file reads **docker/.env**. The repository currently tracks a file at that path, so do not blindly trust or commit it. Inspect it privately; the safe option for a fresh evaluation is to replace it with local-only values derived from **backend/.env.example**. Keep any backup outside the repository.

PowerShell:

```powershell
Copy-Item backend/.env.example docker/.env -Force
```

macOS/Linux:

```bash
cp backend/.env.example docker/.env
```

Edit **docker/.env** and set at least:

```dotenv
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://user:LOCAL_DB_PASSWORD@postgres:5432/customers
POSTGRES_PASSWORD=LOCAL_DB_PASSWORD
SECRET_KEY=GENERATE_A_UNIQUE_LOCAL_SECRET
ADMIN_EMAIL=reviewer-admin@example.test
ADMIN_PASSWORD=Use-A-Strong-Local-Only-Password-123!
```

The password in DATABASE_URL must match POSTGRES_PASSWORD. The database hostname inside Compose is **postgres**, not localhost. Generate a unique SECRET_KEY; never use these illustrative values in a deployed environment. The local administrator password must satisfy the configured password policy.

The Compose file also starts pgAdmin with development-only sample credentials. Do not expose pgAdmin or reuse those credentials outside an isolated local environment.

### 2. Build and start PostgreSQL

```bash
docker compose -f docker/docker-compose.yml build backend
docker compose -f docker/docker-compose.yml up -d postgres
docker compose -f docker/docker-compose.yml ps
```

Wait until PostgreSQL is healthy. It is published on 127.0.0.1:5433 for host-side tools; containers connect to service name **postgres** on port 5432.

### 3. Apply database migrations

```bash
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic upgrade head
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic current
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic heads
```

Use Alembic to create/update the schema. Do not use SQLAlchemy create_all as a replacement for the migration history. Review migration output and back up any non-disposable database before applying changes.

### 4. Create the initial local administrator

```bash
docker compose -f docker/docker-compose.yml run --rm backend uv run python -m admin_script.seed_admin
```

The script reads ADMIN_EMAIL and ADMIN_PASSWORD, requires the default tenant to exist, and creates a trusted platform administrator. If the account already exists, it reports that and does not create a duplicate. Keep the bootstrap password private and change it as required by your evaluation policy.

### 5. Start the application stack

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
```

The Compose stack includes three backend instances, HAProxy as the published HTTP entry point, PostgreSQL, pgAdmin, SLA monitoring, analytics aggregation, report export and webhook delivery workers, plus Prometheus and Blackbox Exporter.

| Service | URL |
|---|---|
| API through HAProxy | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| Liveness | http://localhost:8000/health |
| Readiness (includes database reachability) | http://localhost:8000/ready |
| pgAdmin | http://localhost:5050 |
| Prometheus | http://localhost:9090 |
| HAProxy stats | http://127.0.0.1:8404 |

Useful commands:

```bash
docker compose -f docker/docker-compose.yml logs -f backend
docker compose -f docker/docker-compose.yml logs -f haproxy
docker compose -f docker/docker-compose.yml logs -f report-export-worker
docker compose -f docker/docker-compose.yml down
```

To permanently delete the local database and uploaded-file volumes, use this destructive command only when you intend to reset the disposable environment:

```bash
docker compose -f docker/docker-compose.yml down -v
```

## Alternative: run the API on the host

Use this when you already have PostgreSQL 17 (or a compatible supported PostgreSQL version) with pgvector installed.

1. Create a dedicated local database and ensure the PostgreSQL server has pgvector installed. The migration history requires the vector extension; installing the Python package alone does not install the server extension.
2. From **backend/** install dependencies:

```bash
uv sync --locked
```

3. Copy the environment template:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux use `cp .env.example .env`. Edit **backend/.env** and set DATABASE_URL, SECRET_KEY, ADMIN_EMAIL and ADMIN_PASSWORD. For PostgreSQL started by the supplied Compose file from the host, the port is **5433**; for native PostgreSQL, use that server's configured port (commonly 5432).

4. From **backend/** apply migrations, create the administrator and run the API:

```bash
uv run alembic upgrade head
uv run python -m admin_script.seed_admin
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000/docs. Use Ctrl+C to stop the server.

## Environment configuration

The complete template is **backend/.env.example**. Important variables:

| Variable | Purpose |
|---|---|
| DATABASE_URL | SQLAlchemy PostgreSQL DSN |
| SECRET_KEY | JWT signing secret; use high-entropy unique material |
| ENVIRONMENT | development, testing, staging or production |
| ADMIN_EMAIL / ADMIN_PASSWORD | Initial administrator bootstrap |
| JWT_ACCESS_EXPIRE_MINUTES | Access-token lifetime (default 30 minutes) |
| JWT_REFRESH_EXPIRE_DAYS | Refresh-token lifetime (default 7 days) |
| STORAGE_TYPE / STORAGE_PATH | File storage implementation and local path |
| MAX_FILE_SIZE_MB | Upload size limit |
| AI_PROVIDER / AI_API_KEY / AI_MODEL | AI provider configuration |
| VERIFICATION_PROVIDER | Verification adapter selection |
| OCR_PROVIDER | OCR adapter selection |
| EXTRACTION_PROVIDER | Document extraction adapter selection |
| EMAIL_PROVIDER / SMS_PROVIDER | Communication adapter selection |
| DATA_PROTECTION_KEY | Encryption key for protected application data |
| WEBHOOK_ENCRYPTION_KEY | Key material for protected webhook configuration |
| RATE_LIMIT_ENABLED | Enables the in-process request limiter |
| SECURITY_HEADERS_ENABLED | Enables response security headers |
| DATABASE_REQUIRE_SSL | Database TLS policy for protected environments |
| PUBLIC_BASE_URL | Public API base URL where applicable |

For a local demonstration, mock provider settings are intentional. Production/staging secrets must come from a secret manager, not committed .env files. See [Security baseline](SECURITY_BASELINE.md) and [deployment](../deploy/README.md).

## Authentication and API exploration

1. Open Swagger UI at http://localhost:8000/docs.
2. Call **POST /api/v1/auth/login** with the administrator credentials.
3. Read the access_token from the successful response.
4. Select **Authorize** and provide the access token as a Bearer token.
5. Call **GET /api/v1/me** or **GET /api/v1/profile** to verify the authenticated identity.
6. Use **POST /api/v1/auth/refresh** with a valid refresh token after access-token expiry.

The current FastAPI OpenAPI schema is authoritative. Check endpoint-specific authentication, role requirements, request schemas and status codes before trying protected operations.

## Tests

The suite is under **backend/tests/**. Integration tests use PostgreSQL through TEST_DATABASE_URL. CI uses the pgvector PostgreSQL 17 image, applies migrations, then runs Ruff, Black, MyPy and pytest.

**Use a dedicated disposable database.** Never run tests against production, a shared reviewer database or real customer data.

Example from **backend/** when PostgreSQL is published on host port 5433:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://user:LOCAL_DB_PASSWORD@localhost:5433/finpilot_test"
$env:TEST_DATABASE_URL = $env:DATABASE_URL
uv run alembic upgrade head
uv run pytest -q
```

For bash/zsh, export DATABASE_URL and TEST_DATABASE_URL to the same dedicated test DSN. The database user must be able to create/read/write test records and PostgreSQL must have pgvector available.

Focused commands:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run pytest -q
```

The number and status of tests depend on the checkout and environment. A successful dependency install is not a test result; inspect pytest's final summary and the CI checks for the commit being evaluated.

## Code quality

From **backend/**:

```bash
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pre-commit run --all-files
```

The CI workflow runs locked dependency installation, migrations, Ruff, Black, MyPy and pytest. The local pre-commit configuration contains a platform-specific pytest entry; on non-Windows machines review that hook before relying on pre-commit as a portable command.

## Background jobs

Compose defines separate services for the following modules:

- **app.jobs.sla_monitor**
- **app.jobs.analytics_aggregator**
- **app.jobs.report_export_worker**
- **app.jobs.webhook_delivery_worker**

Do not start duplicate worker processes against the same environment unless concurrency/locking behavior has been reviewed.

## Troubleshooting

| Symptom | Checks |
|---|---|
| Database connection refused | Confirm PostgreSQL is healthy, the correct hostname is used (postgres inside Compose; localhost from host), and ports/credentials match. |
| Migration fails on vector | Use the pgvector PostgreSQL image or install the server-side extension; the Python dependency alone is insufficient. |
| Login fails | Confirm migrations ran, the default tenant exists, bootstrap account exists, and ADMIN_EMAIL/ADMIN_PASSWORD match that account. |
| API is healthy but routes fail | Inspect backend and HAProxy logs, confirm base URL and token, then inspect OpenAPI. |
| Uploaded files disappear | Confirm storage path/volume is persistent and included in backup/restore procedures. |
| Tests fail to connect | Verify TEST_DATABASE_URL and DATABASE_URL point at a dedicated migrated PostgreSQL test database. |
| AI/verification/OCR result is simulated | Mock providers are default; real provider credentials and policy/configuration are separate deployment work. |

## Related documentation

- [Evaluator guide](../docs/EVALUATOR_GUIDE.md)
- [Architecture](../docs/Architecture.md)
- [API standards](../docs/APIStandards.md)
- [Database standards](../docs/DatabaseStandards.md)
- [Security baseline](SECURITY_BASELINE.md)
- [Deployment](../deploy/README.md)
- [Performance testing](../performance/README.md)
- [Disaster recovery](../docs/disaster-recovery/README.md)
