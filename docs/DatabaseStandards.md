# Database standards

## Database platform

PostgreSQL is the primary relational database. SQLAlchemy 2 is used for ORM and session management; psycopg is the PostgreSQL driver; Alembic tracks schema revisions. The migration history uses pgvector, so the PostgreSQL server must have the vector extension installed. The provided development Compose file uses `pgvector/pgvector:pg17`.

## Session and transaction ownership

Use the session dependency in the established request/job lifecycle. Services coordinate multi-step operations and own the relevant transaction/commit boundary. Repositories should encapsulate query and persistence behavior without unexpectedly committing an outer transaction.

For jobs, create and close sessions explicitly and ensure rollback/cleanup is performed when exceptions occur.

## Migration workflow

Run from `backend/`:

```bash
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe schema change"
```

Autogeneration is only a draft. Review the migration manually and confirm:
- Correct `down_revision` and a single intended head unless a merge migration is deliberate.
- Existing data can be migrated safely.
- Constraints, indexes, uniqueness and nullability are correct.
- Defaults and PostgreSQL enum changes are handled safely.
- Upgrade and downgrade paths are coherent.
- Tenant-owned rows are backfilled and constrained without cross-tenant parent/child links.
- The migration runs against a clean database and an existing database.

Do not edit an already applied migration without a coordinated migration-history repair.

## Tenant ownership

Tenant identity must originate from trusted authenticated context. Filter tenant-owned data by tenant ID in queries and writes. Avoid trusting a tenant ID supplied by the client.

For child resources, use a composite database constraint/reference to ensure the child tenant matches its parent tenant where that model supports it. Examples include tenant-scoped ticket comments/attachments/history and feedback history. A UUID alone must never grant access.

Cross-tenant reporting or platform operations must be explicitly guarded by trusted platform-admin claims, target only authorized data, and document the reason tenant filtering is bypassed. Do not make a generic tenant-bypass method available to ordinary tenant roles.

## Indexes and query performance

Add indexes to support measured filters and joins, not speculative ones. Consider compound indexes for tenant-scoped query patterns. Use EXPLAIN/ANALYZE against representative synthetic data and check index selectivity before adding complex indexes. Large reporting and analytics work should avoid unbounded scans and use the project's aggregation/worker patterns.

## Data lifecycle and privacy

Define ownership, retention, deletion, audit and backup expectations for every new table. PII and uploaded files require explicit access controls, retention policy and protection at rest/in transit. Database backups do not automatically include bytes held in the separate file-storage volume.

## Testing

Integration tests need a dedicated PostgreSQL test database and pgvector extension. Apply migrations before tests. Test tenant isolation across reads, inserts, updates, deletes and relationship traversal; verify foreign-key/unique constraints; and validate rollback for multi-step operations.
