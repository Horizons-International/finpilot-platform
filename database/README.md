# Database directory placeholder

The canonical database schema is represented by SQLAlchemy models under **`backend/app/models/`** and Alembic migrations under **`backend/alembic/versions/`**. PostgreSQL is the relational store; pgvector is required by the current migration history.

Use [Database Standards](../docs/DatabaseStandards.md) and [backend setup](../backend/README.md). Do not create or modify production schema outside the reviewed Alembic migration process.
