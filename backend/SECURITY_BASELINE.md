# FinPilot security baseline

This overlay strengthens the existing API security implementation; it does not
replace the existing JWT authentication, tenant filtering, RBAC, audit service,
MFA, API-key permissions, or session-management routes.

## Controls added or hardened

- JWT decode now requires both `exp` and `sub`, and newly issued tokens include
  `iat`. The token's signing algorithm remains explicitly pinned to HS256.
- Access tokens remain short-lived (default 30 minutes); refresh-token lifetime
  is capped at 30 days. Refresh and access tokens remain type-separated.
- Server-side sessions are checked for revocation, expiry, user/tenant ownership,
  and idle timeout. An idle session is revoked and a `SESSION_IDLE_TIMEOUT`
  security event is persisted.
- Passwords up to 72 UTF-8 bytes retain the established bcrypt hash format
  (cost 12). Longer passphrases use a versioned, domain-separated SHA-256 prehash
  before bcrypt, avoiding silent truncation. Verification accepts legacy raw-bcrypt
  hashes; users whose former password exceeded bcrypt's 72-byte limit may need a
  password reset rather than relying on the old truncated-password behavior. Password
  changes and invitation acceptance retain the configurable
  minimum length and complexity checks, with a 128-character upper bound.
- A bounded fixed-window limiter applies per-IP, per-route, and stricter
  authentication/MFA limits. It uses the direct ASGI peer address; it does not
  trust client-provided `X-Forwarded-For` headers.
- Request bodies are capped by `MAX_REQUEST_BODY_BYTES`, including chunked bodies.
- Responses receive anti-sniffing, anti-framing, referrer, permissions, cache,
  cross-origin, and API content-security headers. HSTS is sent only in production.
- Rejected requests (400/401/403/413/422/429) create platform-wide
  `security_events` rows when no trusted identity is available, without storing
  bearer tokens, passwords, query strings, or bodies. Authenticated events stay
  tenant-scoped, and successful accesses update session last-seen timestamps.
- A GitHub Actions job audits the pinned lockfile on pushes, pull requests,
  manual runs, and daily schedule.
- Production startup refuses weak placeholder JWT or administrator bootstrap
  secrets and bounds JWT lifetime settings.

## Environment variables

The previous defaults still work in development and testing. Set these explicitly
in staging/production and store all secrets in the deployment secret manager:

```dotenv
ENVIRONMENT=production
SECRET_KEY=<at-least-32-character-high-entropy-random-secret>
ADMIN_PASSWORD=<unique-12-character-minimum-complex-password>
JWT_ACCESS_EXPIRE_MINUTES=30
JWT_REFRESH_EXPIRE_DAYS=7
SESSION_IDLE_TIMEOUT_MINUTES=60
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_REQUESTS_PER_IP=3000
RATE_LIMIT_REQUESTS_PER_ROUTE=600
RATE_LIMIT_AUTH_REQUESTS=120
MAX_REQUEST_BODY_BYTES=12582912
SECURITY_HEADERS_ENABLED=true
HSTS_MAX_AGE_SECONDS=31536000
```

Generate a secret instead of choosing one manually, for example with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. Do not commit
`.env`, real credentials, signing keys, or webhook encryption keys. Rotate a
signing key through a planned credential rotation because changing `SECRET_KEY`
invalidates tokens and makes existing encrypted MFA seeds unreadable.

## Rate limiting deployment note

The application limiter is process-local and bounded to avoid unlimited memory
use. It is defense in depth for a single process, not a shared quota service.
For multiple Uvicorn workers or replicas, configure equivalent shared limits at
an API gateway/WAF or replace the in-process store with a shared atomic store.
Set the gateway's trusted-proxy configuration explicitly; never trust arbitrary
forwarded-IP headers from clients. Adjust defaults using expected bank traffic
and monitoring before production rollout.

## Suggested rollout

1. Overlay files at the matching paths; review the changes and keep secrets out
   of version control.
2. Install/update dependencies from the existing lockfile with `uv sync --locked`.
3. Run focused tests and then the full suite. The application needs a reachable
   PostgreSQL test database for integration tests.
4. In the backend directory run `uv run alembic heads` and
   `uv run alembic upgrade head`. This overlay adds no database migration.
5. Run the dependency audit locally after exporting the lockfile:

   ```powershell
   uv export --locked --format requirements.txt --all-groups --no-emit-project --output-file requirements-security-audit.txt
   uvx pip-audit --strict --requirement requirements-security-audit.txt
   ```

6. Verify in the deployed environment that HTTPS terminates correctly before
   relying on HSTS, and ensure the API gateway enforces distributed rate limits.

## Test commands

```powershell
uv run pytest tests/unit/test_security_baseline.py -q
uv run pytest tests/integration/test_security_controls.py tests/integration/test_auth.py tests/integration/test_password.py tests/integration/test_security_baseline.py -q
uv run ruff check app/core/config.py app/core/security.py app/middleware/security_monitoring.py app/schemas/auth.py app/services/auth_service.py tests/unit/test_security_baseline.py
uv run mypy app/core/config.py app/core/security.py app/middleware/security_monitoring.py app/schemas/auth.py app/services/auth_service.py
```

Integration tests require the project's configured PostgreSQL test database.
