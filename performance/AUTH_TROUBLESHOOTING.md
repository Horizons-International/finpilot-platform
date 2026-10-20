# Performance login diagnostics

The original smoke/baseline runs failed during `POST /api/v1/auth/login`, before any other API scenario ran. These files improve visibility into that failure; they do not assume whether the cause is credentials, routing, validation, or a server exception.

## Copy-ready installation

From the ZIP, copy the files into the repository root, preserving paths. Overwrite these two existing files:

- `performance/locustfile.py`
- `performance/scripts/run-performance.ps1`

Also copy the new `performance/scripts/check-performance-auth.py` and `performance/AUTH_TROUBLESHOOTING.md` files. No `apply_fix.py` script is required.

## 1. Verify login before loading Locust

Activate `.venv-perf` and run this from the repository root:

```powershell
python .\performance\scripts\check-performance-auth.py
```

The script uses the current session's `PERF_BASE_URL`, `PERF_EMAIL`, and `PERF_PASSWORD`. It never prints the password or returned access token. It shows the HTTP status and a sanitized response detail when available.

## 2. Interpret the diagnostic

- **Connection error / timeout**: check that the service and HAProxy are running, and that `PERF_BASE_URL` points at the intended API entry point.
- **HTTP 401 or 403**: verify that the account exists in the database used by this API and that the password is correct. `performance-admin@example.test` in the README is only an example; the framework does not create that user.
- **HTTP 422**: compare the reported field/location/message with the API's login schema. Do not share raw response bodies that may contain submitted data.
- **HTTP 500**: check the backend container logs using the timestamp/request ID (when provided). This indicates a server-side exception, not a load-capacity result.
- **HTTP 200 but no `data.access_token`**: review the safe JSON key summary; the response envelope may differ from what the load script expects.

## 3. Rerun the smoke test

Only after the diagnostic reports a successful login:

```powershell
.\performance\scripts\run-performance.ps1 -Profile smoke
```

The updated Locust file reports a sanitized reason if authentication fails and asks the runner to stop instead of leaving a headless test running with no usable users. The updated PowerShell runner also treats a populated `*_failures.csv` as a failed test run.

Do not run a baseline until the smoke test completes without request failures. A run containing only failed login requests says nothing about API performance or bottlenecks.
