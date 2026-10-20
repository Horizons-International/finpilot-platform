# FinPilot Performance Test Plan

## Goal

Establish a repeatable process to measure API latency, throughput, error rate, and selected database query durations; use a baseline and runtime telemetry to identify bottlenecks before setting or evaluating capacity targets.

## Environments and safety

- Run first in an isolated test or staging environment, with synthetic/approved test data.
- Record the Git commit, Docker image IDs/tags, host/container limits, database size, fixture counts, and configuration for every run.
- Use a dedicated performance user with the minimum roles required; prefer multiple test users for realistic authentication and tenant load.
- Keep all mutation flags false until the read-heavy smoke and baseline pass.
- Treat AI calls and async report exports as cost-/queue-generating workloads and enable them only after basic stability tests.
- Do not use production customer data in fixtures or exported result files.

## Coverage map

| Area | Workload | Endpoint/query | Default |
|---|---|---|---|
| API health | Liveness/readiness | `GET /health`, `GET /ready` | Enabled |
| Authentication | Initial and repeat login | `POST /api/v1/auth/login` | Enabled with credentials |
| Customer queries | Largest default page | `GET /api/v1/customers?page=1&page_size=100` | Enabled |
| Customer onboarding | Get/start existing customer's workflow | `GET/POST /api/v1/customers/{customer_id}/onboarding` | Read requires fixture; write opt-in |
| Verification | List/create cases | `GET/POST /api/v1/customers/{customer_id}/verification-cases` | Read requires fixture; write opt-in |
| Documents | List/upload nested verification documents and read extraction | Nested document route; `/api/v1/documents/{document_id}/extraction` | Fixture required; writes opt-in |
| Reports | Compliance cases, AML alerts, customer risk, export history | `GET /api/v1/reports/...` | Enabled |
| Report generation | Create async CSV export | `POST /api/v1/reports/exports` | Opt-in |
| AI assistant | Ask and list interactions | `POST /api/v1/ai-assistant/ask`, `GET /api/v1/ai-assistant/interactions` | AI POST opt-in |
| AI document analysis | Document fraud analysis | `POST /api/v1/document-fraud/documents/{document_id}/analyze` | AI opt-in + fixture |
| AI risk analysis | Synthetic transaction sample tied to test customer | `POST /api/v1/transaction-risk-analysis/analyze` | AI opt-in + fixture |
| Database | Aggregate/report-like reads | customers, audit logs, customer status history, latest 100 customers | Separate opt-in command |

## Test phases

1. **Readiness check:** confirm expected routes, DB migrations, test user login, fixture IDs, and file-storage capacity.
2. **Smoke:** one user for about one minute; check no unexpected 5xx/401/403/422, and verify report files are produced.
3. **Baseline:** five users for five minutes with write flags disabled. Keep this report as the initial reference.
4. **Load:** increase users gradually, starting from 10–25 virtual users, and hold each stable for 5–10 minutes. Record application and DB telemetry.
5. **Stress / breaking point:** only on an approved isolated test system, increase concurrency in measured steps until latency/error/queue/CPU/connection saturation violates the agreed guardrail. Stop if the test impacts shared resources.
6. **Feature workloads:** enable one mutation family at a time (verification, document upload, report exports, AI) at low load, verify generated records/queues, and clean up synthetic data as per the staging runbook.
7. **Database benchmark:** run `run-db-benchmark.ps1` only against the designated test DSN; compare repeated times after warm-up and document query plans/index findings separately if needed.
8. **Post-test:** confirm all services healthy, workers drained, fixture effects understood, no unexpected background queues or runaway storage growth, and archive the report outputs.

## Metrics to capture

- HTTP: request count, requests/second, failure count/rate, median, p95, p99, max response time per endpoint.
- Runtime: CPU/memory per container, restarts, network I/O, host saturation.
- Database: active connections, pool exhaustion, slow queries, query time, locks, CPU, I/O, and index/query plans for evidenced slow paths.
- Workers: queue depth, processing delay, failed/retried jobs, output/storage growth.
- AI: provider duration, error/timeout rate, concurrency limits, rate-limit responses, and provider cost where available.

## Bottleneck identification procedure

1. Find endpoints whose p95/p99 and/or error rate regress compared with the baseline.
2. Correlate timestamps with container CPU/memory, database connection/slow-query metrics, worker queue depth, and AI provider latency.
3. Reproduce at the lowest concurrency that shows the symptom.
4. Record the observed evidence, suspected cause, validation experiment, and corrective action in `BOTTLENECK_REGISTER.md`.
5. Rerun the same profile after any fix and compare results under equivalent conditions.

Do not claim a specific bottleneck until results and telemetry support it. Establish pass/fail thresholds with platform owners; this starter bundle does not assume service-level objectives.
