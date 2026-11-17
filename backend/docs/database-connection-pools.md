# Database connection pools and production capacity

FinPilot uses two SQLAlchemy engines because synchronous endpoints/workers and
native-async endpoints have different session APIs. Each engine owns an
independent connection pool in **each Python process**.

## Configuration

The settings are read from the runtime environment (for local Compose, from
`docker/.env`; for the release deployment, from the selected environment file).

| Setting | Default | Meaning |
|---|---:|---|
| `DATABASE_APPLICATION_NAME` | `finpilot` | PostgreSQL `application_name`, visible in `pg_stat_activity` |
| `DATABASE_SYNC_POOL_SIZE` | `3` | Persistent connections kept by each process's synchronous pool |
| `DATABASE_SYNC_MAX_OVERFLOW` | `2` | Temporary synchronous connections above `pool_size` |
| `DATABASE_ASYNC_POOL_SIZE` | `5` | Persistent connections kept by each process's asynchronous pool |
| `DATABASE_ASYNC_MAX_OVERFLOW` | `3` | Temporary asynchronous connections above `pool_size` |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `30` | Maximum wait for a pool connection before checkout fails |
| `DATABASE_POOL_RECYCLE_SECONDS` | `1800` | Replace old connections when they are next checked out |
| `DATABASE_POOL_PRE_PING` | `true` | Check a pooled connection before using it |
| `DATABASE_POOL_LOGGING` | `false` | Enable verbose SQLAlchemy pool checkout/checkin logging for diagnosis |

The sync and async pool sizes are deliberately separate. Both pools use
`pool_pre_ping`, a finite checkout timeout and connection recycling. Recycling
is performed when a connection is checked out; it does not interrupt an active
transaction. `pool_pre_ping` can detect a stale connection before a statement,
but it cannot safely replay an application transaction that failed midway.

## Initial connection budget

The repository's Docker Compose stack currently defines three API instances
(`backend`, `backend-2`, `backend-3`) and four separate database-backed worker
processes (SLA monitor, analytics aggregator, report export, webhook delivery).
The workers currently use the synchronous session factory. The API processes
may use both pools.

With the defaults above:

- One API process can open at most `(3 + 2) + (5 + 3) = 13` pooled connections.
- Three API processes can open at most `3 x 13 = 39` pooled connections.
- One worker process can open at most `3 + 2 = 5` synchronous connections.
- Four worker processes can open at most `4 x 5 = 20` pooled connections.
- The modeled maximum for those seven processes is therefore **59** connections.

This is a capacity estimate, not a measured concurrency requirement or a
universal production recommendation. Add any extra API replicas, worker
replicas, scheduled jobs, migration processes, administrative tools, and other
applications that use the same PostgreSQL server. Allow capacity for PostgreSQL
administration and operational headroom. Confirm the actual server limit rather
than assuming a default value.

Use this formula when the deployment topology changes:

```text
maximum application connections =
    API process count x (sync pool maximum + async pool maximum)
  + sync-only worker process count x sync pool maximum
  + async-only worker process count x async pool maximum
  + other database clients

sync pool maximum  = DATABASE_SYNC_POOL_SIZE + DATABASE_SYNC_MAX_OVERFLOW
async pool maximum = DATABASE_ASYNC_POOL_SIZE + DATABASE_ASYNC_MAX_OVERFLOW
```

A process that creates an engine but never checks out a connection does not
consume a physical PostgreSQL connection. Count the pools that the process
actually uses, and revisit the calculation if workers begin using async
sessions. Each Uvicorn worker process has its own independent pools too.

Do not raise PostgreSQL `max_connections` or the application pool limits
blindly. More connections consume database memory and scheduling resources;
measure checkout pressure and query duration before increasing capacity.

## Inspecting the pools

The helper `get_database_pool_status()` returns counters for the current Python
process without opening a connection. From `backend/`, run:

```powershell
uv run python -c "from pprint import pprint; from app.core.database import get_database_pool_status; pprint(get_database_pool_status())"
```

Inside the local Compose stack, inspect each API container separately:

```powershell
docker compose -f docker/docker-compose.yml exec backend uv run python -c "from pprint import pprint; from app.core.database import get_database_pool_status; pprint(get_database_pool_status())"
docker compose -f docker/docker-compose.yml exec backend-2 uv run python -c "from pprint import pprint; from app.core.database import get_database_pool_status; pprint(get_database_pool_status())"
docker compose -f docker/docker-compose.yml exec backend-3 uv run python -c "from pprint import pprint; from app.core.database import get_database_pool_status; pprint(get_database_pool_status())"
```

The result is local to the process where the command runs; it is not an
aggregate across replicas. A `current_overflow` value below zero is normal when
the pool has not yet opened its configured number of persistent connections.
`checked_out` is the most useful immediate indicator of connections currently
borrowed by that process. Compare it with the pool's maximum and correlate it
with request latency and PostgreSQL activity.

PostgreSQL-side inspection:

```sql
SHOW max_connections;

SELECT
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state
ORDER BY application_name, state;
```

`DATABASE_APPLICATION_NAME` is passed to psycopg for both engines. Give it a
role- or instance-specific value through the runtime environment where possible
(for example, `finpilot-api-1`, `finpilot-api-2`, `finpilot-report-worker`). This
makes it easier to distinguish pools in `pg_stat_activity`. The shared Compose
`.env` intentionally provides a common default; override it per service if you
need per-container attribution.

To investigate pool checkout/checkin behavior temporarily, set
`DATABASE_POOL_LOGGING=true` for the affected process and restart it. This is
verbose and should normally be disabled after diagnosis; do not leave it enabled
indefinitely in a high-volume production deployment.

## Session and transaction practices

- Keep one SQLAlchemy session per request or worker unit of work. Never share a
  `Session` or `AsyncSession` concurrently between tasks.
- Close sessions promptly. The FastAPI dependencies in `app.core.database`
  continue to close sync and async sessions at the end of their dependency scope.
- Do not hold a database transaction open while waiting for an external HTTP,
  AI, email, OCR, or storage provider. Read/claim the data, commit or release
  locks, perform the external work, then open a fresh transaction to persist
  the result where the workflow permits it.
- Keep worker batches bounded. A long-lived worker process may reuse its engine
  and pool, but each unit of work should release its session before sleeping or
  waiting for the next item.
- Do not retry arbitrary writes after a connection error unless the operation
  is explicitly idempotent and the transaction outcome is known.

## Readiness behavior

`/ready` now verifies both the synchronous and asynchronous database paths with
small `SELECT 1` queries. A failure in either pool returns HTTP 503. `/health`
remains a lightweight process liveness endpoint and does not require PostgreSQL.

## Rollout guidance

1. Back up the database and deploy these pool settings to a non-production
   environment first.
2. Check that both `/ready` and `/health` pass.
3. Inspect pool counters in each API process and query `pg_stat_activity` while
   running a representative load test.
4. Watch pool checkout timeouts, PostgreSQL connection count, query latency,
   CPU and memory. Increase pool sizes only when measurements show that waiting
   for connections is the bottleneck and PostgreSQL has safe spare capacity.
5. Repeat the capacity calculation whenever API replicas, Uvicorn workers,
   background workers or other database clients change.

The configured defaults are a conservative starting point for the current
repository Compose topology. They still need validation against the target
PostgreSQL instance, actual workload, connection limits and available memory.
