# FinPilot performance testing

This directory contains Locust API scenarios, helper functions, a PostgreSQL query benchmark and scripts to run/capture test results. Use only an isolated test/staging environment populated with synthetic fixtures.

Read [the test plan](../docs/performance-testing/TEST_PLAN.md) and [the bottleneck register](../docs/performance-testing/BOTTLENECK_REGISTER.md) before starting. A test script or a stored report is not by itself a capacity result; record the exact commit, environment, fixture profile, runtime limits and observed output.

## Requirements

From the repository root, install the dedicated performance dependencies:

```powershell
py -m pip install -r performance/requirements.txt
```

The requirements include Locust. Keep this environment separate from the backend's locked application environment.

## Configure credentials and host

Set the target URL and an existing performance test account. PowerShell example:

```powershell
$env:PERF_BASE_URL = "http://127.0.0.1:8000"
$env:PERF_EMAIL = "performance-user@example.test"
$env:PERF_PASSWORD = "<local-test-password>"
```

The framework does not create this user for you. Confirm that it exists in the database served by the target API and has the minimum roles needed for the selected scenarios. A previously issued access token may be supplied as PERF_ACCESS_TOKEN instead of email/password.

Relevant optional fixture variables include:
- `PERF_CUSTOMER_ID` or `PERF_CUSTOMER_IDS`
- `PERF_VERIFICATION_CASE_ID` or `PERF_VERIFICATION_CASE_IDS`
- `PERF_DOCUMENT_ID` or `PERF_DOCUMENT_IDS`
- `PERF_DOCUMENT_TYPE_ID`
- `PERF_TEST_PHONE_NUMBERS`

The Locust workload uses existing fixture IDs for customer/verification/document-specific paths. Missing fixtures can reduce the exercised route mix; create synthetic fixtures first and record their IDs in the local environment.

## Run profiles

Run from the repository root on Windows PowerShell:

```powershell
.\performance\scripts\run-performance.ps1 -Profile smoke
.\performance\scripts\run-performance.ps1 -Profile baseline
.\performance\scripts\run-performance.ps1 -Profile load
.\performance\scripts\run-performance.ps1 -Profile stress
```

Defaults are one user/one minute for smoke; five users/five minutes for baseline; 25 users/10 minutes for load; and 50 users/10 minutes for stress. You can override host, users, spawn rate and duration with the script parameters. Start with smoke, then baseline; never jump to stress on a shared or production system.

## Mutation and AI safeguards

Write-producing workloads are disabled by default. Enable only against disposable data and one workload at a time using these explicit flags:
- `PERF_ENABLE_CUSTOMER_CREATION`
- `PERF_ENABLE_WORKFLOW_WRITES`
- `PERF_ENABLE_VERIFICATION_WRITES`
- `PERF_ENABLE_DOCUMENT_UPLOADS`
- `PERF_ENABLE_REPORT_WRITES`
- `PERF_ENABLE_AI`

AI calls can generate external provider cost when a real provider is configured. Uploads create storage objects. Report exports create records/files. Make sure cleanup and storage capacity are covered before enabling these workloads.

## Outputs

The runner writes timestamped Locust CSV files and an HTML report under `performance/results/`. Review request count, failure count/rate, median, p95/p99, max latency and per-endpoint results. Preserve raw output and annotate any configuration/fixture differences when comparing runs.

For a database-only benchmark, review `performance/scripts/run-db-benchmark.ps1` and `performance/scripts/benchmark_database.py`. Use the explicit performance test DSN; never point it at a production database.

For diagnostics of authentication startup failures, see [AUTH_TROUBLESHOOTING.md](AUTH_TROUBLESHOOTING.md). A run that failed only at login is not an API performance baseline.
