# FinPilot Backend

FinPilot is a FastAPI backend for financial institutions. It provides customer and tenant management, authentication and role-based access, identity verification, AML/compliance workflows, task and SLA management, analytics, reporting, audit logs, and AI/RAG integration points.

This README covers running the backend locally, initializing the database, trying the API, running background workers, and executing the test suite.

## Contents

- [Features](#features)
- [Technology and prerequisites](#technology-and-prerequisites)
- [Quick start (recommended): Docker Compose](#quick-start-recommended-docker-compose)
- [Alternative: run with a local PostgreSQL installation](#alternative-run-with-a-local-postgresql-installation)
- [Environment configuration](#environment-configuration)
- [Open the API documentation and sign in](#open-the-api-documentation-and-sign-in)
- [Try the main features](#try-the-main-features)
- [Background workers](#background-workers)
- [Run tests](#run-tests)
- [Code quality checks](#code-quality-checks)
- [Troubleshooting](#troubleshooting)

## Features

The current backend includes API modules for:

- JWT authentication, refresh tokens, user profiles, role-based access control, user invitations, and tenant administration.
- Tenant-aware customer records, customer contacts and addresses, and customer audit history.
- Identity verification cases, document types, verification reviews and assignments.
- File storage, customer documents, document review, OCR, and document extraction.
- AML rules, transaction monitoring, compliance cases, and investigation notes.
- Tasks, task assignment rules, workflows, SLA tracking, and operational dashboards.
- Customer, compliance, operations, and executive analytics, plus configurable metrics.
- Compliance reports and asynchronous CSV, Excel, and PDF report exports.
- System configurations, notifications, communication logs, and audit logs.
- AI prompt management, AI interactions, knowledge documents, and retrieval-augmented generation (RAG).
- Risk scoring, customer risk profiles, and risk predictions.

Available routes and request/response schemas are defined in the running OpenAPI documentation. Some integrations are configured to use mock providers by default so the flows can be exercised in a local development environment without external credentials.

## Technology and prerequisites

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) for Python dependency and environment management.
- Docker with Docker Compose, or a local PostgreSQL server.
- Git.

The database must support PostgreSQL's **vector** extension because the migration history includes pgvector. The supplied Docker Compose configuration uses the **pgvector/pgvector** PostgreSQL image.

## Quick start (recommended): Docker Compose

**Recommended for most reviewers:** use Docker Compose to run the API, PostgreSQL with pgvector, and the background workers. You do not need to install PostgreSQL or build/install the pgvector extension on your computer.

### 1. Install Docker and clone the repository

Install Docker Desktop (Windows/macOS) or Docker Engine with the Compose plugin (Linux), then run:

~~~bash
git clone https://github.com/Horizons-International/finpilot-platform.git
cd finpilot-platform
~~~

### 2. Configure the Docker environment

Open **docker/.env**. Ensure it contains the settings below. The Docker database hostname must be **postgres**, not **localhost**, because the API container connects to PostgreSQL over the Compose network.

~~~dotenv
DATABASE_URL=postgresql+psycopg://user:123789@postgres:5432/customers
SECRET_KEY=replace-with-a-long-random-local-secret
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=ChangeThis_Local_Only_123!
ENVIRONMENT=development
~~~

The repository environment file may contain only the database URL, so add any missing required settings. Change the example administrator password and secret to local-only values. Never use these examples in production or commit real credentials to Git.

### 3. Build the Docker image

From the repository root:

~~~bash
docker compose -f docker/docker-compose.yml build
~~~

### 4. Start PostgreSQL and wait for it to be ready

~~~bash
docker compose -f docker/docker-compose.yml up -d postgres
docker compose -f docker/docker-compose.yml exec postgres pg_isready -U user -d customers
~~~

Wait until PostgreSQL reports that it is accepting connections. The provided image is **pgvector/pgvector:pg17**, which includes the PostgreSQL vector extension required by the migration history.

### 5. Run database migrations

~~~bash
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic upgrade head
~~~

Check the current migration revision, if needed:

~~~bash
docker compose -f docker/docker-compose.yml run --rm backend uv run alembic current
~~~

### 6. Create the initial administrator

~~~bash
docker compose -f docker/docker-compose.yml run --rm backend uv run python -m scripts.seed_admin
~~~

The administrator email and password come from **docker/.env**. If that email already exists, the script reports that the administrator already exists.

### 7. Start the API and background workers

~~~bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps
~~~

The Compose stack includes the API, PostgreSQL, pgAdmin, SLA monitor, analytics aggregator, and report-export worker. Open:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI schema: <http://localhost:8000/openapi.json>
- Application health: <http://localhost:8000/health>
- Database readiness: <http://localhost:8000/ready>
- pgAdmin: <http://localhost:5050>

Follow the API logs:

~~~bash
docker compose -f docker/docker-compose.yml logs -f backend
~~~

View logs for an individual worker, for example:

~~~bash
docker compose -f docker/docker-compose.yml logs -f sla-monitor
docker compose -f docker/docker-compose.yml logs -f analytics-aggregator
docker compose -f docker/docker-compose.yml logs -f report-export-worker
~~~

Stop the stack while preserving database and uploaded-file data:

~~~bash
docker compose -f docker/docker-compose.yml down
~~~

To reset the disposable development environment and delete the named data volumes too, run **docker compose -f docker/docker-compose.yml down -v**. This permanently removes database data and uploaded files; do this only when you intend to discard them.

## Alternative: run with a local PostgreSQL installation

Use this option if you specifically want the API process to run on your computer and PostgreSQL is installed locally. Unlike the Docker-first setup above, this approach requires a PostgreSQL installation with the **vector** extension available. If setting up pgvector is difficult, return to the Docker Compose quick start.

### 1. Prepare PostgreSQL and pgvector

Create an empty database for development. Make sure your PostgreSQL installation supports pgvector; the migration creates the extension with **CREATE EXTENSION IF NOT EXISTS vector**, so the extension's server files must already be installed.

### 2. Install backend dependencies

From the repository root:

~~~bash
cd backend
uv sync
~~~

### 3. Create and configure the local environment

On Windows PowerShell:

~~~powershell
Copy-Item .env.example .env
~~~

On macOS or Linux:

~~~bash
cp .env.example .env
~~~

Edit **backend/.env** and set your local database URL plus the required authentication/admin settings. For a typical local PostgreSQL installation:

~~~dotenv
DATABASE_URL=postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:5432/YOUR_DATABASE
SECRET_KEY=replace-with-a-long-random-secret
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=ChangeThis_Local_Only_123!
~~~

Use your actual local PostgreSQL username, password, and database name.

### 4. Apply migrations and create the administrator

Run from the **backend** directory:

~~~bash
uv run alembic upgrade head
uv run python -m scripts.seed_admin
~~~

### 5. Run the API

~~~bash
uv run uvicorn app.main:app --reload
~~~

Open <http://localhost:8000/docs>. Keep the terminal open while testing and stop the server with Ctrl+C.

## Environment configuration

Configuration is loaded from **backend/.env** by the application settings module. At minimum, the following variables are required:

| Variable | Purpose |
| --- | --- |
| **DATABASE_URL** | SQLAlchemy PostgreSQL connection string. |
| **SECRET_KEY** | Secret used to sign JWTs. Use a strong, private value. |
| **ADMIN_EMAIL** | Email used when creating the initial administrator. |
| **ADMIN_PASSWORD** | Password used when creating the initial administrator. |

Other settings in **.env.example** include token lifetimes, storage path and size limits, AI configuration, verification/OCR/extraction providers, communication providers, SLA monitoring, and report-export limits.

The example configuration selects mock providers for AI, verification, OCR, extraction, email, and SMS. This is useful for local demonstrations and tests. Real external providers require their respective provider settings and credentials.

## Open the API documentation and sign in

1. Open <http://localhost:8000/docs>.
2. Expand **POST /api/v1/auth/login** and select **Try it out**.
3. Enter the administrator credentials configured in **.env**, for example:

   ~~~json
   {
     "email": "admin@example.com",
     "password": "ChangeThis_Local_Only_123!"
   }
   ~~~

4. Execute the request. A successful response contains an **access_token** and a **refresh_token** in the response data.
5. Select **Authorize** in Swagger UI and provide the access token. Use the access token for protected API operations. Access tokens expire; use **POST /api/v1/auth/refresh** with a valid refresh token to obtain a new one.

You can also call the API with an HTTP client such as curl, Postman, or Insomnia. For protected requests, send the header **Authorization: Bearer <access_token>**.

## Try the main features

Use Swagger UI to exercise the routes below. Expand each operation, read the displayed request schema, select **Try it out**, and execute it. Required fields and valid enum values are shown by the API schema.

### 1. Check the application and database

- **GET /health** checks that the API is running.
- **GET /ready** checks that the API can reach PostgreSQL.

A successful readiness response should report that the database is connected.

### 2. Check authentication and the current user

- **POST /api/v1/auth/login** obtains tokens.
- **GET /api/v1/me** returns the authenticated user's basic profile.
- **GET /api/v1/profile** and **PUT /api/v1/profile** read and update profile information.
- **POST /api/v1/auth/refresh** refreshes an access token.

Authenticate in Swagger before testing protected routes.

### 3. Create a customer

After signing in as the administrator, expand **POST /api/v1/customers** and use the request schema shown in Swagger. A typical customer payload looks like this:

~~~json
{
  "first_name": "Jane",
  "middle_name": "Demo",
  "last_name": "Customer",
  "date_of_birth": "1990-05-15",
  "nationality": "US",
  "country_of_residence": "US",
  "email": "jane.customer.demo@example.com",
  "phone_number": "+249912345678",
  "status": "new"
}
~~~

Use a unique email address and phone number if you repeat the test. After creating a customer, try:

- **GET /api/v1/customers** to search/list customers.
- **GET /api/v1/customers/{customer_id}** to retrieve a particular customer.
- **PUT /api/v1/customers/{customer_id}** to update one.
- **PATCH /api/v1/customers/{customer_id}/status** to change status.

Copy the returned customer ID into subsequent requests that require a customer ID.

### 4. Explore verification and documents

Use the customer verification routes listed in Swagger to create a verification case, upload a supported document, and inspect or review the case. The exact route paths and request fields are available in the **Verification Cases**, **Documents**, **OCR**, **Extraction**, and **Document Review** tags.

The default verification, OCR, and extraction providers are mocks. This allows development flows to be exercised without connecting an external provider.

### 5. Explore AML, compliance, tasks, and workflows

Relevant route groups include:

- **/api/v1/aml-rules** — create and manage AML rules.
- **/api/v1/transaction-monitoring** — run transaction monitoring operations.
- **/api/v1/compliance-cases** — create and review compliance cases.
- **/api/v1/tasks** — create, assign, update, and complete tasks.
- The **Workflows** tag — inspect and run configured workflows.

Use the schemas displayed by Swagger to provide request bodies and enum values. Access is role-based; a user may receive **403 Forbidden** when their role is not allowed to perform an operation.

### 6. Explore dashboards, analytics, and reports

- The **Dashboard** and **Executive Dashboard** tags expose dashboard views.
- The **Analytics** tag exposes customer, compliance, and operations analytics.
- **GET /api/v1/reports/compliance-cases** generates a compliance-case report.
- **GET /api/v1/reports/aml-alerts** generates an AML alert report.
- **GET /api/v1/reports/customer-risk** generates a customer risk report.
- The report-export routes under **/api/v1/reports/exports** can generate CSV, Excel, or PDF exports and expose export status and download operations.

Some scheduled analytics or SLA figures depend on the background workers described below. Large report exports are processed asynchronously when the configured threshold is exceeded.

### 7. Explore tenants and administrative configuration

The initial administrator is a platform administrator. Use the **Tenants**, **Users**, and **System Configurations** tags to explore tenant administration, user management, and configuration operations. Tenant and role restrictions apply to protected resources.

### 8. Explore AI and knowledge retrieval

Use the **AI Prompts**, **AI Assistant**, **AI Usage**, **Knowledge Documents**, and **RAG** tags in Swagger. The local example configuration uses a mock AI provider and does not require an external API key. Real model responses require configuring a supported provider and its credentials.

For development only, the repository includes a script that creates baseline AI prompts and assignments:

~~~bash
uv run python -m tests.seed
~~~

Run it from the **backend** directory after migrations and only against your development database. It inserts seed data; it is not required to start the API.

## Background workers

The API can be run without starting every worker, but some scheduled and queued behavior depends on them. Start each worker in a separate terminal from the **backend** directory, with the same **.env** and database available:

~~~bash
uv run python -m app.jobs.sla_monitor
~~~

~~~bash
uv run python -m app.jobs.analytics_aggregator
~~~

~~~bash
uv run python -m app.jobs.report_export_worker
~~~

These workers monitor SLA deadlines, aggregate analytics, and process queued report exports respectively. Keep them running when testing behavior that relies on background processing.

## Run tests

**Use a dedicated test database.** The integration tests create and modify database records. Never point **TEST_DATABASE_URL** at a development or production database.

### Recommended: run tests in Docker

Create a separate test database inside the Compose PostgreSQL container once:

~~~bash
docker compose -f docker/docker-compose.yml exec postgres psql -U user -d customers -c "CREATE DATABASE testdb;"
~~~

If **testdb** already exists, skip this step. Apply the migrations to the test database, then run pytest in a one-off backend container:

~~~bash
docker compose -f docker/docker-compose.yml run --rm -e DATABASE_URL=postgresql+psycopg://user:123789@postgres:5432/testdb backend uv run alembic upgrade head
docker compose -f docker/docker-compose.yml run --rm -e TEST_DATABASE_URL=postgresql+psycopg://user:123789@postgres:5432/testdb backend uv run pytest -q
~~~

For a smaller test run, replace **pytest -q** with **pytest tests/unit -q** or **pytest tests/integration -q**. These commands use the test database within Docker and do not require local PostgreSQL or pgvector installation.

### Alternative: run tests from your computer

If Python dependencies are installed in **backend**, create **testdb** in the supplied PostgreSQL container as shown above, then run the tests from the **backend** directory.

#### Windows PowerShell

~~~powershell
$env:DATABASE_URL = "postgresql+psycopg://user:123789@localhost:5432/testdb"
uv run alembic upgrade head
Remove-Item Env:DATABASE_URL

$env:TEST_DATABASE_URL = "postgresql+psycopg://user:123789@localhost:5432/testdb"
uv run pytest -q
~~~

When finished, clear the variable:

~~~powershell
Remove-Item Env:TEST_DATABASE_URL
~~~

#### macOS or Linux

~~~bash
DATABASE_URL="postgresql+psycopg://user:123789@localhost:5432/testdb" uv run alembic upgrade head
TEST_DATABASE_URL="postgresql+psycopg://user:123789@localhost:5432/testdb" uv run pytest -q
~~~

## Code quality checks

Run from the **backend** directory:

~~~bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run black --check app tests
uv run mypy app
~~~

Run tests separately as described above so it is clear which database they use.

## Troubleshooting

- **Settings validation says a required field is missing:** confirm **backend/.env** contains **DATABASE_URL**, **SECRET_KEY**, **ADMIN_EMAIL**, and **ADMIN_PASSWORD**. In Docker mode, check the environment file configured for the containers.
- **PostgreSQL connection refused:** make sure the database container is running with **docker compose -f docker/docker-compose.yml ps** and that the URL uses **localhost** for a host-run API or **postgres** for a container-run API.
- **The pgvector extension is unavailable:** use the supplied **pgvector/pgvector** image or install pgvector for your own PostgreSQL server before running the migrations.
- **Login fails:** confirm the administrator was seeded after the migrations and that the email and password match the values in **.env**.
- **A protected endpoint returns 401:** log in again and use a valid, unexpired access token.
- **An endpoint returns 403:** check the authenticated user's role and the operation's required permissions.
- **Tests cannot connect or fail with missing tables:** confirm **testdb** exists, set **TEST_DATABASE_URL** to that database, and run Alembic migrations against the same database before running pytest.

For development troubleshooting, check the API terminal logs and the PostgreSQL logs:

~~~bash
docker compose -f docker/docker-compose.yml logs -f postgres
~~~

For API behavior and request validation details, start with the interactive documentation at <http://localhost:8000/docs>.
