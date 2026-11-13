# FinPilot asynchronous architecture review

**Reviewed baseline:** `main` at `f84ae18032aa1f752082f2b2c8eb8fe5a8a298cc` (13 November 2026).

## Current position

FinPilot has both SQLAlchemy engines and session factories:

- `async_engine` / `AsyncSessionLocal` for native async request handlers and middleware.
- `engine` / `SessionLocal` for legacy synchronous request handlers, services, workers, scripts, maintenance tasks and test fixtures.

Keeping both is intentional. The synchronous engine should **not** be removed yet.

## Remaining synchronous consumers

The repository still contains synchronous route/service paths, including security and profile management, sandbox and sales-demo operations, data-protection administration, case priorities, risk predictions and risk-scoring rules, partner onboarding, entity intelligence, transaction anomalies, AI model metrics, AI prompt administration, product-usage analytics, transaction-risk analysis and AML investigation assistance.

Some routers use ordinary `def` endpoints. FastAPI runs synchronous endpoint functions in its worker thread pool, so those functions do not directly block the ASGI event loop. Their synchronous dependencies and SQLAlchemy `Session` lifetimes must remain aligned with that execution model until they are migrated together.

The following compatibility-bridge API consumers also remain and should be migrated before the bridge is retired:

- `backend/app/api/verification_reports.py`
- `backend/app/api/ai_assistant.py` (decision-explanation history operations)

The synchronous AI provider/service stack is still used by legacy AI flows such as regulatory assistance, AML investigation assistance, risk recommendations and transaction-risk analysis. The native async provider has been integrated into the async document-fraud service only; this is a safe incremental migration rather than a global switch.

## Middleware and exception auditing

API-key usage, protected-read auditing and security monitoring use async sessions. The HTTP 404 access-denied exception audit must also use `middleware_async_session` and `AsyncAuditService`; an async exception handler must not issue synchronous SQLAlchemy calls on the event loop.

Middleware audit writes are best-effort: a failed audit write must not turn an otherwise successful response into a 500, and an access-denied audit failure must not replace the original 404 response.

## Background workers and scripts

The following entry points intentionally retain synchronous sessions today:

- `app.jobs.sla_monitor`
- `app.jobs.analytics_aggregator`
- `app.jobs.data_retention`
- `app.jobs.report_export_worker`
- `app.jobs.webhook_delivery_worker`
- `app.maintenance.encrypt_existing_data`
- `admin_script.seed_admin`
- `scripts/cleanup_expired_sandbox_accounts.py`

These run as separate worker processes or one-off maintenance/administrative commands. They do not need to be converted merely for consistency. If a worker is migrated, give it an explicit event-loop lifecycle, use one `AsyncSession` per concurrent task, and preserve its advisory-lock, retry, tenant-scope and shutdown behavior.

## AI client lifecycle

The async OpenAI adapter uses the official `AsyncOpenAI` client and is scoped with `async with AsyncAIService(...)`. This closes the underlying HTTP client after each current async document-fraud request. That is safe and leak-resistant. A shared lifespan-managed client/pool can be considered later if profiling shows client setup overhead or connection churn is material; do not introduce global mutable client state without defining ownership, concurrency and shutdown behavior.

Synchronous AI consumers should continue to use the synchronous adapter from synchronous service/route execution until those service workflows are migrated. Do not pass a synchronous SQLAlchemy `Session` into an async AI endpoint or share one `AsyncSession` across concurrent tasks.

## Retirement criteria for the synchronous database engine

Do not remove `engine`, `SessionLocal` or `get_db` until all of the following are true:

1. No production API route, dependency, middleware, service, worker, script or maintenance entry point imports or constructs a synchronous SQLAlchemy `Session`.
2. The two remaining `run_sync_in_tenant` API consumers have native async implementations and the bridge has no callers.
3. The synchronous AI service/provider consumers and all other synchronous business-service dependencies have been migrated or deliberately isolated in a separately managed process with its own database runtime.
4. Tests, seed utilities, backup/restore tooling and operational scripts have been migrated or explicitly retain a separately provisioned sync engine by design.
5. CI includes a repository-wide guard against new production imports of `SessionLocal`/`get_db` outside an approved allowlist.
6. Load tests, pool-capacity tests, worker concurrency tests and shutdown tests pass in the target deployment topology.

## Recommended order

1. Keep the async exception-handler audit change and its regression tests.
2. Migrate remaining high-traffic synchronous API areas in coherent router/service/repository slices, retaining sync endpoints where they are intentionally dispatched to the thread pool.
3. Migrate the remaining bridge users and then remove `async_service_bridge.py` only when it has no callers.
4. Move synchronous AI consumers to `AsyncAIService` as each owning service becomes async.
5. Decide separately whether each background worker benefits from async I/O; preserve worker isolation and reliability guarantees.
6. Re-run performance tests and inspect pool saturation, p95/p99 latency and event-loop blocking before considering sync-engine retirement.
