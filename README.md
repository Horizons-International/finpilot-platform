# FinPilot Platform

FinPilot is a backend-first platform for financial institutions and fintech operators. This repository contains the Python/FastAPI application, PostgreSQL persistence and migrations, tenant-aware business services, background jobs, Docker infrastructure, deployment workflows, and security/performance/disaster-recovery tooling.

**Evaluation scope:** assess this repository as a backend/API platform. The root frontend and mobile directories are placeholders; working customer-facing web and mobile clients are not included.

## Start here

- [Evaluator guide](docs/EVALUATOR_GUIDE.md): setup, demo sequence, verification checklist and evidence map.
- [Known limitations](docs/KNOWN_LIMITATIONS.md): scope boundaries and items to verify before production.
- [Architecture](docs/Architecture.md): layers, runtime components and repository map.
- [Backend setup](backend/README.md): install, database, admin bootstrap, API and test instructions.
- [Documentation index](docs/README.md): feature, engineering and operations guides.
- [Deployment](deploy/README.md): environment separation and release procedures.
- [Security testing](security-testing/README.md), [performance testing](performance/README.md), [disaster recovery](docs/disaster-recovery/README.md).

## Capability overview

The backend exposes APIs for authentication and session controls; tenant/organization administration; customer onboarding and history; identity verification and document review; file storage, OCR and extraction; AML, transaction monitoring and risk scoring; compliance cases and investigations; tasks, workflows and SLA monitoring; analytics and reporting; API keys, integrations and webhooks; a synthetic sandbox and developer portal; billing foundations; customer success, support and feedback; and AI prompt, knowledge retrieval and assistant workflows.

The running OpenAPI schema is authoritative for exact routes, schemas and permissions in the selected checkout.

## Architecture

```text
Client / API consumer
        |
        v
FastAPI routers (/api/v1)
        |
        +---- Authentication, authorization and tenant context
        |
        v
Application services
        |
        v
Repositories and SQLAlchemy models
        |
        v
PostgreSQL (+ pgvector where required)

Provider adapters: AI, OCR, extraction, verification, email and SMS
Background jobs: SLA monitoring, analytics aggregation, report exports,
                 webhook delivery
Runtime: Docker Compose, HAProxy, PostgreSQL and observability services
```

The canonical code is under **backend/app/**. Root-level folders such as **api/**, **models/** and **services/** are placeholders, not the active Python package.

## Technology

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, psycopg, Alembic, pgvector, uv, pytest, Ruff, Black, MyPy, Docker Compose, HAProxy, Prometheus and Blackbox Exporter.

## Quick start

Use the Docker Compose path in [backend/README.md](backend/README.md). It starts PostgreSQL with pgvector and routes the API through HAProxy. In brief: install Git, Docker Compose v2, Python 3.12 and uv; clone the repository; privately inspect and replace any existing local Docker environment file; configure unique local credentials; apply Alembic migrations; create a local administrator; start the stack; then open http://localhost:8000/docs and check /health and /ready.

The backend guide contains the full commands and a local PostgreSQL alternative.

## Quality checks

From **backend/**, CI installs the locked environment, applies migrations, and runs:

```bash
uv sync --locked
uv run alembic upgrade head
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest -q
```

Integration tests require a reachable PostgreSQL test database with pgvector. Use a dedicated disposable database, never production or real customer data. A workflow's existence is not proof that the commit currently under review passed; inspect the check results for that exact commit.

## Security and data handling

The project includes JWT authentication, role checks, tenant-aware repositories/query context, audit and security events, session controls, request limits, security headers and data-protection configuration. These controls still require environment-specific review, monitoring, secret management and independent security testing before production.

**Repository hygiene warning:** the current Git tree contains **docker/.env**, although .env files are listed in .gitignore. I did not open or reproduce that file because it may contain credentials. Before external evaluation, inspect it privately, replace it with a template-only file, remove it from version control, and rotate any real secret that has ever been committed. Removing a file from the latest commit does not remove it from Git history.

Do not use real customer or bank data in demos, fixtures, test runs or screenshots.

## Scope and limitations

- The shipped product surface here is the backend/API; there is no working frontend or mobile app.
- AI, verification, OCR, extraction, email and SMS default to mock providers unless real integrations are configured.
- Sandbox webhook delivery is simulated; the sandbox does not send outbound requests.
- Billing is a commercial ledger foundation; it does not collect or settle payments.
- The in-process rate limiter is not a distributed quota service.
- Multiple API containers on one host do not provide host-level high availability.
- Test procedures are present, but their existence is not evidence of a current passing security or performance assessment.

Read [Known limitations](docs/KNOWN_LIMITATIONS.md) before treating a feature as production-ready.

## License

See [LICENSE](LICENSE).
