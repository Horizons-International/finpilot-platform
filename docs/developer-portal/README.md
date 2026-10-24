# FinPilot Developer Portal

The browser portal is served at `/developer-portal` by the `developer_portal` FastAPI router. It links to the live Swagger UI (`/docs`), ReDoc (`/redoc`), and machine-readable OpenAPI schema (`/openapi.json`).

## Deploy and access

1. Copy the files in this package to the corresponding paths in the repository.
2. Apply the `integration/main_py.patch` change, or add the import and `app.include_router(developer_portal_router)` lines shown in the patch to `backend/app/main.py`.
3. Ensure your Docker image/container includes the entire `backend/app/static/developer_portal/` directory. The assets are loaded from paths relative to `app/api/developer_portal.py`.
4. Apply any pending Alembic migrations as normal; this portal reuses the existing API and does not add a database table or migration.
5. Open `https://<your-host>/developer-portal`. Confirm `/health`, `/docs`, `/redoc`, and `/openapi.json` all work on the target deployment.

## What this adds

- Developer-oriented guides and cURL examples for JWT login, customer APIs, verification, risk predictions, API keys, and webhooks.
- A request playground that sends requests directly from the browser to the configured base URL; it is not a server-side proxy.
- An API-key manager backed by the existing `/api/v1/api-keys` endpoints: sign in, list/create/revoke keys, and inspect key usage.
- Direct links to the live OpenAPI-derived endpoint catalogue.

No backend dependency is added. The static assets use vanilla HTML, CSS, and JavaScript.

## Sandbox and security notes

- Set the playground base URL to the bank's actual sandbox/test deployment. This package does **not** provision a separate sandbox server or sandbox database.
- `/health` is the unauthenticated smoke-test request. Use synthetic data when testing write routes.
- For regular user endpoints, authenticate with a user access JWT via `Authorization: Bearer <token>` and follow endpoint-specific role requirements.
- The partner integration routes explicitly using API-key authentication expect `X-API-Key: <secret>`. At the time this guide was prepared, `GET /api/v1/integrations/customers` requires `customers:read`. Do not assume every endpoint accepts an API key.
- API-key creation/listing/revocation/usage calls are JWT-authenticated and restricted to Administrator or Organization Admin roles. A newly created key's secret is returned once only.
- The key manager keeps the administrator access token only in JavaScript memory. A page reload clears it; it is not written to `localStorage` or cookies. The request playground does not persist credentials either.
- Do not use this portal to enter production secrets on shared computers. Restrict access at the network/identity layer if this portal should not be public.
- If a developer points the browser tool to a different host, that host needs correct TLS and CORS policy. The same-origin deployment is the simplest setup.

## Endpoints covered in the portal

| Area | Routes shown | Authentication in the current API |
|---|---|---|
| Auth | `POST /api/v1/auth/login` | Public login endpoint |
| Customers | `POST /api/v1/customers`, `GET /api/v1/customers`, `GET /api/v1/customers/{customer_id}` | JWT and role checks |
| Partner customer reads | `GET /api/v1/integrations/customers`, `GET /api/v1/integrations/customers/{customer_id}` | `X-API-Key`, permission `customers:read` |
| Verification | `POST/GET /api/v1/customers/{customer_id}/verification-cases`, `POST /api/v1/customers/{customer_id}/verification` | JWT and role checks |
| Risk predictions | `POST /api/v1/customers/{customer_id}/risk-predictions`, `GET /api/v1/customers/{customer_id}/risk-predictions/latest`, `GET /api/v1/customers/{customer_id}/risk-predictions` | JWT and role checks |
| Webhooks | `POST/GET /api/v1/webhooks` | JWT; administrator role for subscription management |
| API key administration | `/api/v1/api-keys` and subroutes | JWT; Administrator or Organization Admin |

The exact live schema may differ by deployed release and is authoritative. Use `/docs` for all schemas, optional parameters, response models, and status codes.
