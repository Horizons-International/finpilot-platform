# FinPilot Platform

AI-powered platform for banks, fintech companies, money transfer operators, and financial institutions.

## Overview

FinPilot Platform is a backend foundation designed to provide a secure, maintainable, and extensible platform for financial applications.


## Project Structure

```text
finpilot-platform/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── storages/
│   │   └── utils/
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── uv.lock
│
├── frontend/
├── mobile/
├── docs/
├── database/
├── docker/
├── scripts/
├── infrastructure/
├── tests/
└── .github/
```

The backend follows a layered architecture:

```text
API Layer
    ↓
Service Layer
    ↓
Repository Layer
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

Supporting components such as authentication, configuration, logging, storage, audit logging, and reusable utilities are provided through shared application modules.

## Backend

The backend provides the platform foundation, including:

* Authentication and JWT token management
* Role-based access control
* User management
* Customer management
* Profile management
* File storage
* Audit logging
* Health and readiness monitoring
* Database migrations
* Reusable utilities
* Centralized configuration
* Structured error handling and logging

## Technology Stack

### Backend

* Python 3.12
* FastAPI
* Pydantic
* SQLAlchemy
* Alembic
* PostgreSQL
* Uvicorn
* psycopg

### Development and Quality

* uv
* pytest
* Ruff
* Black
* MyPy
* pre-commit

### Infrastructure

* Docker
* Docker Compose
* PostgreSQL
* pgAdmin

## Prerequisites

The following tools are required for local development:

* Python 3.12
* uv
* Docker Desktop
* Git

PostgreSQL can be run directly during local development or through the Docker Compose environment.

## Getting Started

Clone the repository:

```bash
git clone <repository-url>
cd finpilot-platform
```

Install backend dependencies:

```bash
cd backend
uv sync
```

Configure the required environment variables in the backend environment configuration (.env).

After configuration, database migrations can be applied with:

```bash
uv run alembic upgrade head
```

## Environment Configuration

Application configuration is centralized through environment variables.

Configuration includes values for:

* Database connection
* Application environment
* Application version
* JWT authentication
* Access-token configuration
* Refresh-token configuration
* File storage
* Maximum file size
* Allowed file types
* Administrator seed configuration

Sensitive values such as passwords, JWT secrets, and database credentials should not be committed to Git.

Use environment-specific configuration for development, testing, and Docker deployments.

## Database

The application uses PostgreSQL as its primary relational database.

SQLAlchemy provides the ORM and database session management, while Alembic provides version-controlled database migrations.

Database access follows the application's dependency-injection pattern:

```text
FastAPI endpoint
      ↓
get_db()
      ↓
SQLAlchemy Session
      ↓
Service
      ↓
Repository
      ↓
PostgreSQL
```

Database transactions are managed at the service/application boundary. Repositories perform database operations without unnecessarily committing the surrounding transaction.

## Database Migrations

Run the latest migrations:

```bash
uv run alembic upgrade head
```

Check the current migration revision:

```bash
uv run alembic current
```

Create a new migration when the database model changes:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Review generated migrations before applying them.

## Running the Application

From the `backend` directory:

```bash
uv run uvicorn app.main:app --reload
```

The API provides interactive OpenAPI documentation through Swagger UI.

The API documentation is available at:

```text
http://localhost:8000/docs
```

The OpenAPI schema is available at:

```text
/openapi.json
```

## Docker Development

The project includes a Docker-based development environment containing the application and supporting infrastructure.

From the `docker` directory, start the environment with:

```bash
docker compose up --build
```

To run the environment in the background:

```bash
docker compose up --build -d
```

Stop the environment with:

```bash
docker compose down
```

View running containers:

```bash
docker compose ps
```

View backend logs:

```bash
docker compose logs backend
```

Follow backend logs:

```bash
docker compose logs -f backend
```

The Docker environment has been verified with the application's API endpoints, authentication, database connectivity, user management, profile management, file management, and health checks.

## Health Monitoring

The application provides two health endpoints.

### Application Health

```http
GET /health
```

This verifies that the application process is running.

### Application Readiness

```http
GET /ready
```

The readiness endpoint verifies that the application can successfully communicate with PostgreSQL.

A successful readiness response indicates that the application and database are available.

## Authentication

Authentication is provided through JWT-based access and refresh tokens.

### Login

```http
POST /api/v1/auth/login
```

A successful login returns the authentication tokens required to access protected endpoints.

### Refresh Token

```http
POST /api/v1/auth/refresh
```

A valid refresh token can be used to obtain a new access token.

### Change Password

```http
POST /api/v1/auth/change-password
```

Authenticated users can change their own password.

Authentication events are integrated with the audit framework where applicable.

## Role-Based Access Control

The platform provides role-based authorization.

Protected endpoints use shared authorization dependencies to restrict access based on the authenticated user's role.

Administrative functionality requires the Administrator role.

Examples include:

* User management
* Administrative endpoints
* File deletion
* Other privileged operations

Authorization is enforced at the API boundary using reusable security dependencies.

## User Management

The platform provides administrator-controlled user management.

Available operations include:

```text
POST   /api/v1/users
GET    /api/v1/users
GET    /api/v1/users/{user_id}
PUT    /api/v1/users/{user_id}
PATCH  /api/v1/users/{user_id}/status
DELETE /api/v1/users/{user_id}
```

User deletion uses the platform's soft-delete behavior where applicable.

User management operations are recorded through the audit logging framework.

## Profile Management

Authenticated users can access and update their profile.

```text
GET /api/v1/profile
PUT /api/v1/profile
```

Profile information includes user identity and contact information supported by the current user model.

## Customer Management

Customers are a core business entity in FinPilot. The customer entity provides a centralized source of customer information that can be referenced by future identity verification, compliance, risk, and operational modules.

```text
POST /api/v1/customers
GET /api/v1/customers/{id} 
PUT /api/v1/customers/{id}
```

## File Storage

The platform provides a reusable file-storage service.

Supported operations include:

```text
POST   /api/v1/files
GET    /api/v1/files/{file_id}
DELETE /api/v1/files/{file_id}
```

The file service handles:

* File type validation
* File size validation
* Physical file storage
* File metadata persistence
* File retrieval
* File deletion
* Audit logging
* Database rollback
* Physical-file cleanup when an operation fails

The current implementation uses local storage through the storage abstraction.

The storage layer is designed around a reusable storage interface so additional storage implementations can be introduced later.

## Audit Logging

The platform provides a centralized audit framework for recording security- and user-related events.

Examples include:

* User creation
* User updates
* User status changes
* User deletion
* File uploads
* File downloads
* File deletion
* Authentication-related events

Audit records can include:

* User ID
* Email
* Event type
* IP address
* User agent
* Resource type
* Resource ID
* Timestamp

Audit logging is integrated into service operations rather than being duplicated across individual API endpoints.

## Error Handling

Application errors are handled through centralized error-handling mechanisms.

The API uses consistent response structures and appropriate HTTP status codes.

Common application errors include:

* `400 Bad Request`
* `401 Unauthorized`
* `403 Forbidden`
* `404 Not Found`
* `500 Internal Server Error`
* `503 Service Unavailable`

Database errors are logged with exception details while API responses avoid exposing unnecessary internal implementation information.

## Configuration Management

Application configuration is centralized rather than being hard-coded throughout the application.

Configuration values are accessed through the application's settings module.

This includes:

* Database configuration
* Environment
* Application metadata
* Authentication settings
* File-storage configuration
* File limits
* Allowed file types

Environment-specific values should be supplied through environment configuration rather than committed source code.

## Reusable Utilities

The project includes shared utility modules for common functionality.

Current utility areas include:

* Date and time helpers
* String normalization
* Validation helpers
* File-name utilities
* Environment helpers
* Response helpers
* Pagination helpers
* Error helpers
* Shared constants
* Shared enums

Utilities should contain generic reusable logic rather than business-specific behavior.

Business logic belongs in services, while reusable generic behavior belongs in the utility layer.

## Testing

The project uses pytest for automated testing.

Run the complete test suite:

```bash
uv run pytest
```

Run a specific test file:

```bash
uv run pytest tests/integration/test_users.py
```

For file-related tests:

```bash
uv run pytest tests/integration/test_file.py
```

The test suite includes integration coverage for areas such as:

* Authentication
* User management
* Profile management
* File upload
* File download
* File deletion
* File validation
* Role-based authorization

Test-specific physical files are cleaned up after file tests to prevent test artifacts from remaining in the development storage directory.

## Code Quality

The project uses Ruff, Black, and MyPy.

Run Ruff:

```bash
uv run ruff check .
```

Run Black's formatting check:

```bash
uv run black --check .
```

Run MyPy:

```bash
uv run mypy .
```

Run all pre-commit checks:

```bash
uv run pre-commit run --all-files
```

Code should pass the configured quality checks before being committed.

## Git Workflow

Development should follow the project's Git workflow.

Before creating a pull request:

1. Pull the latest changes.
2. Implement the change in an appropriate branch.
3. Run the test suite.
4. Run code-quality checks.
5. Run pre-commit.
6. Review the changes.
7. Commit the changes.
8. Push the branch.
9. Open a pull request.
10. Resolve CI failures before merging.

Generated files, local environment files, secrets, and development artifacts should not be committed.

## CI/CD

The project includes CI/CD automation through the repository's GitHub configuration.

The CI pipeline is responsible for validating the project before changes are merged.

The pipeline should verify the same fundamental quality requirements used during local development, including:

* Dependency installation
* Code quality
* Type checking
* Automated tests

A pull request should not be considered ready for merge while required CI checks are failing.

## Documentation

Project documentation is maintained under the `docs/` directory.

Recommended documentation areas include:

```text
docs/
├── architecture.md
├── api.md
├── development.md
├── configuration.md
└── phase-1-review.md
```

The root README provides the entry point for developers, while detailed technical documentation belongs in `docs/`.

## Phase 1 Platform Foundation

Phase 1 establishes the technical foundation required for Phase 2 development.

The following foundation areas have been implemented and verified:

* [x] Secure authentication
* [x] JWT access and refresh tokens
* [x] Role-based access control
* [x] User management
* [x] Profile management
* [x] Project structure
* [x] Coding standards
* [x] PostgreSQL database connectivity
* [x] SQLAlchemy integration
* [x] Alembic migrations
* [x] Docker development environment
* [x] Centralized configuration
* [x] Logging
* [x] Error handling
* [x] Health monitoring
* [x] Readiness monitoring
* [x] File storage service
* [x] Audit logging framework
* [x] Reusable utilities
* [x] Automated tests
* [x] Code-quality tooling
* [x] CI/CD pipeline
* [x] Documentation

Phase 1 is considered complete and provides a stable foundation for implementing business features in Phase 2.
