# FinPilot Backend

FinPilot is a FastAPI backend for financial institutions. It provides customer and tenant management, authentication and role-based access, identity verification, AML/compliance workflows, task and SLA management, analytics, reporting, audit logs, and AI/RAG integration points.

This README covers running the backend locally, initializing the database, trying the API, running background workers, and executing the test suite.

## Contents

- [Features](#features)
- [Technology and prerequisites](#technology-and-prerequisites)
- [Quick start: run the API locally](#quick-start-run-the-api-locally)
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

## Quick start: run the API locally

These instructions run FastAPI on your computer and PostgreSQL in Docker. Run the Docker commands from the repository root.

### 1. Clone the repository

~~~bash
git clone https://github.com/Horizons-International/finpilot-platform.git
cd finpilot-platform
~~~

### 2. Start PostgreSQL

~~~bash
docker compose -f docker/docker-compose.yml up -d postgres
docker compose -f docker/docker-compose.yml ps
~~~

The supplied development database container is configured with database **customers**, user **user**, and password **123789**. These are development-only credentials; do not reuse them in a real environment. If you use your own PostgreSQL server instead, create an empty database and ensure pgvector is installed.

### 3. Install backend dependencies

~~~bash
cd backend
uv sync
~~~

### 4. Create and configure the environment file

On Windows PowerShell:

~~~powershell
Copy-Item .env.example .env
~~~

On macOS or Linux:

~~~bash
cp .env.example .env
~~~

Open **backend/.env** and set at least the following values. The database URL below matches the supplied PostgreSQL Docker service when the API is running on your host machine.

~~~dotenv
DATABASE_URL=postgresql+psycopg://user:123789@localhost:5432/customers
SECRET_KEY=replace-with-a-long-random-secret
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=ChangeThis_Local_Only_123!
~~~

Keep the **.env** file private. Use a unique secret and password for your environment, and never commit real credentials or production secrets to Git.

### 5. Apply database migrations

Make sure PostgreSQL is running, then from the **backend** directory run:

~~~bash
uv run alembic upgrade head
~~~

The migrations create the database schema and the default tenant. Check the applied migration revision with:

~~~bash
uv run alembic current
~~~

### 6. Create the initial administrator

~~~bash
uv run python -m scripts.seed_admin
~~~

The script creates an active platform administrator using **ADMIN_EMAIL** and **ADMIN_PASSWORD** from **.env**. If that email already exists, the script reports that the administrator already exists.

### 7. Start the API

~~~bash
uv run uvicorn app.main:app --reload
~~~

The local API is now available at:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI schema: <http://localhost:8000/openapi.json>
- Application health: <http://localhost:8000/health>
- Database readiness: <http://localhost:8000/ready>

Keep the server terminal open while trying the API. Stop it with Ctrl+C.

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

### Run the full Docker Compose stack (optional)

The Compose file also defines the API, PostgreSQL, pgAdmin, and the three background workers. To run all services in containers, configure **docker/.env** before starting them. It must include the required application settings from **backend/.env.example**; the container-to-container database URL must use hostname **postgres**, for example:

~~~dotenv
DATABASE_URL=postgresql+psycopg://user:123789@postgres:5432/customers
SECRET_KEY=replace-with-a-long-random-secret
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=ChangeThis_Local_Only_123!
~~~

From the repository root:

~~~bash
docker compose -f docker/docker-compose.yml up --build -d
docker compose -f docker/docker-compose.yml ps
~~~

Apply migrations and seed the administrator in the backend container:

~~~bash
docker compose -f docker/docker-compose.yml exec backend uv run alembic upgrade head
docker compose -f docker/docker-compose.yml exec backend uv run python -m scripts.seed_admin
~~~

Open the API at <http://localhost:8000/docs>. The configured pgAdmin service is available at <http://localhost:5050>. Do not use the example container credentials or secrets for a production deployment.

To stop the containers:

~~~bash
docker compose -f docker/docker-compose.yml down
~~~

To stop and delete the PostgreSQL data volume as well, use **docker compose -f docker/docker-compose.yml down -v**. This permanently deletes the database data stored in that volume; only do this when you intend to reset the development environment.

## Run tests

**Use a dedicated test database.** The integration tests create and modify database records. Never set **TEST_DATABASE_URL** to a development or production database.

The supplied PostgreSQL container creates the **customers** database on first startup. Create a separate **testdb** database once, from the repository root:

~~~bash
docker compose -f docker/docker-compose.yml exec postgres psql -U user -d customers -c "CREATE DATABASE testdb;"
~~~

If **testdb** already exists, skip this step. Make sure the test database has the current schema by applying the Alembic migrations to it. From the **backend** directory, use the matching connection string below.

### Windows PowerShell

~~~powershell
$env:DATABASE_URL = "postgresql+psycopg://user:123789@localhost:5432/testdb"
uv run alembic upgrade head
Remove-Item Env:DATABASE_URL

$env:TEST_DATABASE_URL = "postgresql+psycopg://user:123789@localhost:5432/testdb"
uv run pytest -q
~~~

Keep **TEST_DATABASE_URL** set while running more test commands. When finished, clear it:

~~~powershell
Remove-Item Env:TEST_DATABASE_URL
~~~

### macOS or Linux

~~~bash
DATABASE_URL="postgresql+psycopg://user:123789@localhost:5432/testdb" uv run alembic upgrade head
TEST_DATABASE_URL="postgresql+psycopg://user:123789@localhost:5432/testdb" uv run pytest -q
~~~

Run selected parts of the test suite when diagnosing an issue:

~~~bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
~~~

The commands assume **TEST_DATABASE_URL** is already set in your shell for the test database.

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
