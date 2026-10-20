# Performance Test Results

> **Recorded execution:** 2026-10-20. This section captures the results reported from the current FinPilot performance-testing session. Some environment metadata and the numeric Docker telemetry were not included in the console excerpts, so they are marked as unrecorded rather than inferred. Keep this record for the current test cycle; use the reusable blank template at the end for future runs.

## Recorded run metadata

- Run date: 2026-10-20
- Time zone: workstation output appears to be Africa/Khartoum (UTC+02:00)
- Environment: local Docker high-availability setup; exact environment classification (test vs. staging) not confirmed
- Git commit / release: Not recorded
- API base URL: `http://127.0.0.1:8000` (reported default, through local HAProxy)
- Backend image IDs/tags: Not recorded
- Database version and dataset size: Not recorded
- Host CPU / RAM / container limits: Not recorded
- Test account role(s): Not recorded; credentials were configured through environment variables and are intentionally omitted
- Write-producing tasks / AI generation: Disabled by default for these runs; AI interaction history GET endpoint was exercised
- Database benchmark DSN label: `localhost/testdb` (as printed by the benchmark; credentials omitted)
- Database benchmark iterations: 5 samples per query
- Database statement timeout: 15,000 ms

## Executive summary

| Run | Configuration | Requests | Failures | Error rate | Median | p95 | p99 | Max reported | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Smoke (before dependency fix) | 1 user; 1 user/s; 1 min configured | 96 | 1 | 1.04% | 20 ms aggregated | 220 ms | 280 ms | 280 ms | **Failed** — AI interaction history returned HTTP 500. Superseded by the successful post-fix run below. |
| Smoke (after dependency fix) | Smoke profile; exact concurrency/duration from script configuration | 93 | 0 | 0.00% | 20 ms | 250 ms | 490 ms | 494 ms in request table; percentile view approximates 490 ms | **Passed HTTP-failure check** — `--run-time limit reached`; exit code 0. Small sample (6 login requests) means upper percentiles are noisy. |
| Baseline (after dependency fix) | 5 users; spawn 1/s; 5 min | 2,341 | 0 | 0.00% | 18 ms | 210 ms | 230 ms | 256 ms in request table; percentile view approximates 260 ms | **Passed HTTP-failure check** — Locust exit code 0. |
| Load (after dependency fix) | 25 users; spawn 5/s; 10 min | 23,352 | 0 | 0.00% | 20 ms | 260 ms | 280 ms | 460 ms | **Passed load execution / zero-failure check** — `--run-time limit reached`; exit code 0. Capacity sign-off still depends on agreed SLOs and telemetry review. |
| Database benchmark | 5 iterations; read-only queries | 20 query samples total | 0 query errors | N/A | N/A | See query table | N/A | See query table | **Completed** — all four query groups reported `error=None`. |

- Pre-fix smoke report: `performance/results/smoke-<earlier-timestamp>.html` (exact path not supplied)
- Post-fix smoke report: `performance/results/smoke-20261020-053853.html`
- Post-fix smoke CSV prefix: `performance/results/smoke-20261020-053853`
- Baseline report: `performance/results/baseline-20261020-050541.html`
- Baseline CSV prefix: `performance/results/baseline-20261020-050541`
- Completed load report: `performance/results/load-20261020-054148.html`
- Completed load CSV prefix: `performance/results/load-20261020-054148`
- Database JSON report: `performance/results/db-benchmark-20261020-051334.json`
- Docker stats CSV: a CSV was recorded while the baseline ran concurrently, but the filename and numeric contents were not included in the supplied output. Add the exact path and review its values before using it for bottleneck conclusions; no numeric resource conclusion is recorded here.
- Agreed SLO/pass-fail latency guardrails: Not yet recorded. Zero HTTP failures is a useful stability check, but alone it does not establish capacity targets.

## Baseline endpoint results

The values below are from the successful five-user baseline output. Percentiles are Locust's approximations; the displayed max and percentile views differ slightly due to reporting/rounding.

| Endpoint/task name | Requests | Failures / % | Avg ms | Median ms | p95 ms | p99 ms | Max ms (request table) | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `GET /api/v1/ai-assistant/interactions` | 80 | 0 / 0% | 18 | 18 | 23 | 26 | 25 | Passed after optional retrieval dependency change. |
| `GET /api/v1/customers (page_size=100)` | 405 | 0 / 0% | 24 | 24 | 29 | 33 | 37 | p99 remains below 40 ms in this run. |
| `GET /api/v1/reports/aml-alerts` | 179 | 0 / 0% | 18 | 19 | 22 | 25 | 24 | No request failures. |
| `GET /api/v1/reports/compliance-cases` | 254 | 0 / 0% | 18 | 18 | 22 | 24 | 39 | Isolated high max relative to median; correlate with telemetry before drawing conclusions. |
| `GET /api/v1/reports/customer-risk` | 151 | 0 / 0% | 19 | 19 | 24 | 30 | 30 | No request failures. |
| `GET /api/v1/reports/exports` | 189 | 0 / 0% | 18 | 19 | 21 | 24 | 27 | Measures export history reads, not export generation. |
| `GET /api/v1/transaction-risk-analysis` | 71 | 0 / 0% | 18 | 18 | 21 | 29 | 28 | Read endpoint; generation/analysis POST was not enabled. |
| `GET /health` | 417 | 0 / 0% | 4 | 4 | 5 | 6 | 6 | Health endpoint. |
| `GET /ready` | 443 | 0 / 0% | 5 | 5 | 7 | 8 | 11 | Readiness endpoint. |
| `POST /api/v1/auth/login` | 152 | 0 / 0% | 219 | 220 | 240 | 250 | 256 | Slowest endpoint by response time; monitor in the full load run. |
| **Aggregated** | **2,341** | **0 / 0%** | **27** | **18** | **210** | **230** | **256** | Reported throughput 7.81 req/s. Aggregate percentiles are strongly influenced by login latency. |

## Post-fix smoke endpoint results

The completed smoke run reported 93 total requests and no failures. It reached the configured runtime limit and exited with code 0. Because there were only six login samples and the overall test was brief, high percentiles are sensitive to single outliers and are not a reliable SLO measurement.

| Endpoint/task name | Requests | Failures / % | Avg ms | Median ms | p95 ms | p99 ms | Max ms (request table) | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `GET /api/v1/ai-assistant/interactions` | 3 | 0 / 0% | 73 | 98 | 99 | 99 | 99 | Very small sample. |
| `GET /api/v1/customers (page_size=100)` | 17 | 0 / 0% | 68 | 27 | 300 | 300 | 304 | One slow request dominates the average and upper percentile. |
| `GET /api/v1/reports/aml-alerts` | 6 | 0 / 0% | 22 | 22 | 36 | 36 | 35 | Very small sample. |
| `GET /api/v1/reports/compliance-cases` | 9 | 0 / 0% | 25 | 20 | 47 | 47 | 47 | Very small sample. |
| `GET /api/v1/reports/customer-risk` | 8 | 0 / 0% | 27 | 22 | 50 | 50 | 50 | Very small sample. |
| `GET /api/v1/reports/exports` | 7 | 0 / 0% | 38 | 20 | 77 | 77 | 76 | Very small sample. |
| `GET /api/v1/transaction-risk-analysis` | 4 | 0 / 0% | 42 | 49 | 54 | 54 | 54 | Very small sample. |
| `GET /health` | 16 | 0 / 0% | 4 | 4 | 5 | 5 | 4 | Health endpoint. |
| `GET /ready` | 17 | 0 / 0% | 5 | 6 | 6 | 6 | 6 | Readiness endpoint. |
| `POST /api/v1/auth/login` | 6 | 0 / 0% | 278 | 250 | 490 | 490 | 494 | Six samples only; do not compare this smoke p95 directly with a steady-state profile. |
| **Aggregated** | **93** | **0 / 0%** | **45** | **20** | **250** | **490** | **494** | Reported 1.57 req/s; this brief smoke run is a failure check, not a throughput certification. |

## Completed load endpoint results

The completed load run reached `--run-time limit reached`, exited with code 0, and reported zero request failures. The profile was configured for 25 users, spawn rate 5 users/s, and 10 minutes. The final Locust summary showed 23,352 requests and 38.95 req/s. The arithmetic average based on 23,352 requests over 10 minutes is approximately 38.92 req/s, consistent with the reported rounded throughput.

| Endpoint/task name | Requests | Failures / % | Avg ms | Median ms | p95 ms | p99 ms | Max ms (request table) | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `GET /api/v1/ai-assistant/interactions` | 856 | 0 / 0% | 21 | 21 | 29 | 42 | 160 | p99 remains low; one rare higher response. |
| `GET /api/v1/customers (page_size=100)` | 4,157 | 0 / 0% | 29 | 28 | 37 | 48 | 187 | p99 under 50 ms; rare max outlier. |
| `GET /api/v1/reports/aml-alerts` | 1,617 | 0 / 0% | 21 | 21 | 29 | 38 | 153 | p99 38 ms; rare max outlier. |
| `GET /api/v1/reports/compliance-cases` | 2,487 | 0 / 0% | 21 | 20 | 27 | 38 | 168 | p99 38 ms; investigate rare max only if telemetry correlates. |
| `GET /api/v1/reports/customer-risk` | 1,671 | 0 / 0% | 22 | 21 | 29 | 42 | 153 | p99 42 ms; rare max outlier. |
| `GET /api/v1/reports/exports` | 1,687 | 0 / 0% | 22 | 21 | 29 | 37 | 145 | Measures export-history reads, not export generation. |
| `GET /api/v1/transaction-risk-analysis` | 872 | 0 / 0% | 21 | 20 | 27 | 41 | 146 | Read endpoint; generation/analysis POST was not enabled. |
| `GET /health` | 4,189 | 0 / 0% | 4 | 4 | 7 | 10 | 107 | Low p99, but isolated maximum warrants telemetry correlation if reproducible. |
| `GET /ready` | 4,107 | 0 / 0% | 6 | 6 | 9 | 13 | 85 | Low p99, but isolated maximum warrants telemetry correlation if reproducible. |
| `POST /api/v1/auth/login` | 1,709 | 0 / 0% | 264 | 260 | 300 | 340 | 460 | Higher latency than five-user baseline; cause not established. |
| **Aggregated** | **23,352** | **0 / 0%** | **35** | **20** | **260** | **280** | **460** | Reported throughput 38.95 req/s; login latency strongly influences aggregate upper percentiles. |

## Load-vs-baseline observations

- Login latency increased with the higher-concurrency profile: baseline p95/p99 were 240/250 ms at five users; completed load p95/p99 were 300/340 ms at 25 users. Both runs had zero recorded request failures. This is an observed latency increase, not proof of a specific authentication, application, or database bottleneck.
- During the completed load profile, read/report endpoint p95 values ranged from 27–37 ms and p99 values from 37–48 ms. The larger maximum values are infrequent outliers; compare their timestamps to resource telemetry before prioritizing them.
- Aggregate p95 is 260 ms and aggregate p99 is 280 ms, largely reflecting the portion of requests spent on login. Use per-endpoint percentiles for endpoint-level decisions.
- A zero-failure 10-minute run at 25 users is a useful stability result, but it is not a universal capacity guarantee. Define SLO thresholds and repeat with a representative production-sized dataset before capacity sign-off.

## Database benchmark results

The script reported five samples per query and `error=None` for each. Values are milliseconds.

| Query group | Samples | Mean ms | p95 ms | Max ms | Error |
|---|---:|---:|---:|---:|---|
| `customers_count` | 5 | 1.105 | 3.614 | 3.614 | None |
| `audit_logs_count` | 5 | 0.863 | 2.579 | 2.579 | None |
| `customer_status_history_count` | 5 | 0.838 | 2.723 | 2.723 | None |
| `customers_latest_100` | 5 | 0.590 | 1.450 | 1.450 | None |

The benchmark completed and wrote `performance/results/db-benchmark-20261020-051334.json`. These small, read-only query timings do not establish performance of all database workloads. The command emitted a warning that `.venv-perf` did not match the backend project's `backend\.venv` and would be ignored by `uv`; despite this warning, the benchmark completed successfully. Confirm the intended interpreter/dependencies for repeatability.

## Runtime telemetry

| Component | Result available | Evidence/path | Interpretation |
|---|---|---|---|
| Docker containers (baseline capture) | CSV recorded; metrics not supplied in the console excerpt | `performance/results/docker-stats-<timestamp>.csv` — replace with exact filename | Not yet correlated quantitatively with endpoint latency. Review CPU, memory, network I/O and block I/O by container. |
| HAProxy/load balancer | Not summarized | Same capture if included | No conclusion yet. |
| PostgreSQL | Benchmark query timings available; CPU, connections, locks and I/O not summarized | Database JSON report above; Docker CSV if it includes PostgreSQL | No DB bottleneck demonstrated by the four measured read queries, but broader DB capacity is unassessed. |
| Report/document workers | Not summarized | Not supplied | No conclusion; async generation/write tests were disabled. |
| AI provider/adapter | No AI generation was enabled in these runs | Not applicable to the tested read-only AI interaction-history endpoint | No conclusion about AI generation or embedding latency/cost. |

## Findings and decision

1. **Functional blocker fixed and smoke-rechecked:** the initial `GET /api/v1/ai-assistant/interactions` 500 was traced to eager construction of `RetrievalService`/`EmbeddingService` when the configured provider was not OpenAI. The optional retrieval dependency change is followed by a successful smoke run (93 requests, zero failures) and the endpoint had zero failures in both baseline (80/80 successes) and completed load (856/856 successes).
2. **Smoke, baseline, database benchmark, and configured load execution passed their no-failure checks:** post-fix smoke 93/93; five-user baseline 2,341/2,341; 25-user ten-minute load 23,352/23,352; database benchmark four query groups with five samples each and `error=None`. Load output explicitly confirms `--run-time limit reached` and exit code 0.
3. **Measured behavior under load:** 23,352 requests over the configured ten minutes, reported 38.95 req/s, and zero request failures. Load aggregate median/p95/p99 were 20/260/280 ms. Read/report endpoint p95 was 27–37 ms and p99 37–48 ms. Login p95/p99 rose from 240/250 ms at baseline to 300/340 ms in load; this warrants investigation but does not identify a cause.
4. **Capacity sign-off remains conditional:** the resource CSV's exact filename and numeric values have not been supplied for analysis. Correlate CSV timestamps with login and rare endpoint max-latency outliers; inspect per-container CPU/memory, restarts, PostgreSQL connections/pool usage, and I/O. Do not claim a CPU, memory, DB, or network bottleneck without that evidence.
5. **Acceptance thresholds not defined in this record:** agree target p95/p99 latency, minimum throughput, and error-rate thresholds with the platform owner before declaring overall capacity acceptable. Use a production-representative dataset and test environment for formal capacity certification.
6. **Data cleanup/workload scope:** these profiles tested reads and login; create/upload/export-generation/AI-generation writes were disabled by default. Confirm no optional write flags were enabled for the specific runs.

- Overall decision: **Performance-testing framework and test execution are demonstrated. Smoke, baseline, database benchmark, and the configured 10-minute / 25-user load run passed with zero recorded failures. Do not treat the result as formal capacity sign-off until runtime telemetry is reviewed and SLO guardrails are agreed.**
- Follow-up: review the exact Docker stats CSV; agree service-level guardrails; archive the HTML/CSV/JSON evidence; consider a separate stress test above 25 users and opt-in feature-specific tests for document, export-generation, and AI-generation workloads if required by the user story.

---

# Reusable blank run template

Copy this section for each future run and replace the placeholders.

## Run metadata

- Run ID/date/time (timezone):
- Environment (test/staging):
- Git commit / release:
- API base URL (no credentials):
- Backend image ID/tag:
- Database version and dataset size:
- Host CPU / RAM / container limits:
- Test account role(s), fixture count (no account identifiers/secrets):
- Test profile (smoke/baseline/load/stress/feature/database):
- Virtual users / spawn rate / duration / wait-time range:
- Enabled write/AI flags:
- Locust HTML report path:
- Locust CSV prefix/path:
- Database JSON report path (if run):
- Docker stats CSV path:

## Summary

- Requests:
- Requests/second (state whether instantaneous or whole-run average):
- Failure count and error rate:
- Median response time:
- p95 response time:
- p99 response time:
- Maximum response time:
- Agreed pass/fail guardrails:
- Result: PASS / FAIL / INCONCLUSIVE

## Endpoint results

| Endpoint/task name | Requests | Failures / % | RPS | Median ms | p95 ms | p99 ms | Max ms | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `GET /ready` | | | | | | | | |
| `POST /api/v1/auth/login` | | | | | | | | |
| `GET /api/v1/customers` | | | | | | | | |
| Reports | | | | | | | | |
| Verification/documents | | | | | | | | |
| AI workloads (if enabled) | | | | | | | | |

## Runtime telemetry

| Component | CPU | Memory | Restarts | Connections/queue | Evidence/path |
|---|---:|---:|---:|---:|---|
| backend replicas | | | | | |
| HAProxy/load balancer | | | | | |
| PostgreSQL | | | | | |
| Report/document workers | | | | | |
| AI provider/adapter | | | | | |

## Findings and decision

- Observed bottlenecks (evidence only):
- Error/timeout patterns:
- Suspected cause and evidence:
- Follow-up issue(s)/owner:
- Data cleanup performed:
- Test stopped early? Why?
- Comparison with prior baseline:
- Approval/reviewer:
