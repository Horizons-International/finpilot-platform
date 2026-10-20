# FinPilot Security Testing Preparation

This package prepares a safe, repeatable security-assessment workflow. It adds a dedicated local test stack, black-box API security smoke tests, Python static analysis, dependency auditing, a security checklist, and a vulnerability-tracking process.

> **Scope and authorization:** Run these tests only against the isolated stack provided here or another explicitly authorized non-production target. Never run them against production or a bank/customer environment without written scope approval. The Compose stack uses test-only credentials and a deliberately low per-route limit; do not reuse those settings outside this lab.

## 1. What's included

- `docker/docker-compose.security-test.yml`: separate PostgreSQL and API services; only the API is published to loopback. PostgreSQL stays private on the Compose network. It does not load the application's normal `.env` file or mount local source/data volumes.
- `security-testing/tests/test_security_smoke.py`: checks key security response headers, unauthenticated access boundaries, request validation, and rate-limit enforcement.
- `security-testing/scripts/start-security-test-env.ps1` and `stop-security-test-env.ps1`: start/initialize/stop the isolated environment.
- `security-testing/scripts/run-security-tests.ps1`: run the black-box tests and save JUnit output.
- `security-testing/scripts/run-static-scans.ps1`: run Bandit against backend Python code and `pip-audit` against the backend's resolved environment; JSON reports are written to `security-testing/results/`.
- `SECURITY_TEST_PLAN.md`, `SECURITY_TEST_CHECKLIST.md`, `FINDING_TRIAGE_AND_REMEDIATION.md`, and `VULNERABILITY_REGISTER.csv`: assessment plan, evidence checklist, remediation workflow, and finding tracker.

## 2. Prerequisites

- Docker Desktop with Docker Compose v2.
- Python 3.12+ and `uv` available on `PATH` (the repo already uses `backend/pyproject.toml` and `backend/uv.lock`).
- Network access to package advisory services when running `pip-audit` for the first time.
- Port `18080` available on `127.0.0.1`. PostgreSQL is not exposed on the host; the backend reaches it as `security-postgres:5432` inside Compose.

## 3. Start the isolated security-test environment

Run from the repository root in PowerShell:

```powershell
.\security-testing\scripts\start-security-test-env.ps1
```

The script builds the backend and a dedicated Postgres container, applies Alembic migrations to the isolated test database, and waits for `/health` on `http://127.0.0.1:18080`. PostgreSQL is intentionally not published to a Windows host port, so there is no need to free port `55432`.

The stack uses a named volume `finpilot-security-test_security_test_db_data`. Do not put real or production-like sensitive data into it. The Compose rate limit is intentionally `3` requests per route so the test can verify a `429`; this is a lab-only setting.

## 4. Run executable API security checks

```powershell
.\security-testing\scripts\run-security-tests.ps1
```

Equivalent direct command:

```powershell
uv run --project backend --group dev pytest security-testing/tests -q --junitxml=security-testing/results/security-tests.xml
```

The tests use only localhost and read-only or invalid-input requests. The rate-limit probe calls a nonexistent URL four times and expects the fourth request to return `429 Too Many Requests` with `Retry-After`. The unauthenticated tests generate security audit events in the isolated test database.

## 5. Run source and dependency scanners

```powershell
.\security-testing\scripts\run-static-scans.ps1
```

This runs Bandit and `pip-audit`. Read the JSON reports; non-zero scanner exit codes can mean findings were detected, or that a scan failed. Verify the console output and report before deciding which occurred. Do not suppress findings simply to get a green run. The scans need internet access to download the tool and query current dependency advisories.

The static scanners are a starting point, not a substitute for container/image scanning, manual code review, tenant-isolation testing, or an authorized penetration test. Image scanning with an approved tool such as Trivy and a passive DAST review with OWASP ZAP can be added under the organization's assessment policy.

## 6. Stop the environment

```powershell
.\security-testing\scripts\stop-security-test-env.ps1
```

To delete only the lab's named database volume as well:

```powershell
.\security-testing\scripts\stop-security-test-env.ps1 -RemoveData
```

The deletion switch is explicit because it destroys the lab database. The script uses the dedicated Compose project name `finpilot-security-test`; it does not issue `docker compose down` against the normal stack.

## 7. Track findings

Record each distinct finding in `VULNERABILITY_REGISTER.csv` and create a Markdown report from `VULNERABILITY_REPORT_TEMPLATE.md`. Use a stable ID (`SEC-0001`), severity, affected component/endpoint, evidence, impact, owner, remediation target date, fix reference, and retest result. Follow the status definitions and escalation guidance in `FINDING_TRIAGE_AND_REMEDIATION.md`.

The register intentionally starts empty. No vulnerability scan has been run by packaging these files, so this package does **not** claim that the codebase is vulnerability-free.

## 8. Completion criteria for the preparation task

- [ ] Isolated environment starts and its migrations complete.
- [ ] API security smoke tests execute and produce JUnit evidence.
- [ ] Bandit and dependency audit execute and reports are reviewed.
- [ ] Security checklist has evidence/owners recorded.
- [ ] Findings, if any, are added to the register and receive remediation statuses.
- [ ] A human reviewer approves the assessment scope and decides whether a full penetration test is ready to begin.


## If pytest reports `httpx.ConnectError` / `WinError 10061`

The smoke tests make real HTTP requests to the isolated API at `http://127.0.0.1:18080`; they are not in-process FastAPI tests. A connection-refused error means the API is not listening, so the assertions have not run. Start the stack first:

```powershell
.\security-testing\scripts\start-security-test-env.ps1
.\security-testing\scripts\run-security-tests.ps1
```

If startup fails or the API is not reachable, run:

```powershell
.\security-testing\scripts\diagnose-security-test-env.ps1
```

Inspect `docker compose ... ps -a` and the `security-backend` logs. An `Exited` backend, failed Alembic migration, or an unhealthy startup needs to be resolved before running pytest. The test fixture and PowerShell runner now perform a connectivity preflight so this condition is reported explicitly.

