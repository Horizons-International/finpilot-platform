# Architecture decision log

This page records notable design choices visible in the repository. It is a living index, not a replacement for formal ADRs. Each entry should be revisited when the implementation or requirements change.

## D-001 — Layered FastAPI backend

**Decision visible in code:** the active backend is organized into API routers, schemas, services, repositories and SQLAlchemy models under `backend/app/`.

**Reasoning to preserve:** keep HTTP transport concerns separate from domain rules and persistence; support unit tests and multiple API consumers.

**Review considerations:** prevent service/repository responsibilities from leaking into routers; keep access checks consistent across entry points.

## D-002 — PostgreSQL and Alembic are authoritative

**Decision visible in code:** SQLAlchemy manages relational persistence and Alembic stores schema changes. The migration history requires pgvector.

**Reasoning to preserve:** relational integrity, versioned schema change and repeatable environments.

**Review considerations:** migrations must be tested against clean and existing databases; server-side pgvector availability is a prerequisite.

## D-003 — Tenant-scoped business data

**Decision visible in code:** tenant context and tenant-aware query/repository patterns are used across business modules. Platform operations can intentionally cross tenant boundaries under trusted administrative context.

**Reasoning to preserve:** prevent one financial institution from accessing another institution's records.

**Review considerations:** independently test every resource path and privileged bypass, including nested child resources and bulk/reporting queries.

## D-004 — Provider abstraction with mock defaults

**Decision visible in code:** provider settings select adapters for AI, verification, OCR, extraction and communications; the example environment uses mock providers.

**Reasoning to preserve:** local development and tests should not require external accounts or incur provider costs.

**Review considerations:** mock behavior is not real integration assurance; production must configure, monitor and acceptance-test chosen providers.

## D-005 — Separate worker processes

**Decision visible in code:** SLA, analytics, report export and webhook delivery are defined as separate job modules and Compose services.

**Reasoning to preserve:** isolate periodic/long-running work from latency-sensitive request handling.

**Review considerations:** define concurrency, idempotency, retry/dead-letter and monitoring behavior for the real deployment topology.

## D-006 — Docker Compose for local multi-service development

**Decision visible in code:** the development Compose file provides HAProxy, multiple API containers, PostgreSQL/pgvector, workers and observability services.

**Reasoning to preserve:** enable a repeatable integration environment with visible service boundaries.

**Review considerations:** one host is not high availability; production must use independent failure domains and appropriately resilient storage/database services.

## D-007 — Commercial ledger separated from payment processing

**Decision visible in feature documentation:** billing plans, subscription assignments, usage calculations and invoice snapshots exist without payment collection or settlement.

**Review considerations:** payment provider, tax, credits, reconciliation and accounting integrations are separate product requirements.

## Maintaining this log

For material architectural changes, add an entry with: decision ID/date, status (proposed/accepted/superseded), context, decision, alternatives, consequences, implementation references and tests/evidence. Link a dedicated ADR for high-impact changes.
