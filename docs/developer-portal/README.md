# FinPilot Developer Portal

The developer portal is served by the FastAPI application at `/developer-portal`. It is already registered in the current backend; it is not a separate frontend application or an overlay that needs to be copied into place.

## Implementation

- Router: `backend/app/api/developer_portal.py`
- Static assets: `backend/app/static/developer_portal/`
- Router registration: `backend/app/main.py`
- No database migration is required for the portal itself.

The endpoint serves a static HTML, CSS and JavaScript browser tool. It also links to the live Swagger UI (`/docs`), ReDoc (`/redoc`) and machine-readable OpenAPI (`/openapi.json`).

## Access and use

After starting the API, open:

```text
http://localhost:8000/developer-portal
```

The portal contains developer guides and cURL examples for authentication, customers, verification, risk predictions, API keys and webhooks, plus a request playground and API-key management view.

## Authentication and security

- The playground sends requests directly from the browser to the selected base URL; it is not a server-side proxy.
- The API-key manager uses JWT authentication for key administration routes; the raw key secret is shown only at creation.
- Partner integration routes that explicitly require API keys expect the documented API-key header and permission (for example, `customers:read` for the partner customer read integration). Do not assume all protected routes support API keys.
- The page keeps its current access token in JavaScript memory; reloading clears it. Do not use shared/public devices for real credentials.
- Use synthetic data and test keys. Never paste production keys, customer personal data or document contents into a demo playground.
- A different target host needs valid TLS and an appropriate CORS policy. Same-origin deployment is preferred.
- Restrict portal access at network/identity level if your institution does not want the documentation playground to be publicly accessible.

## Troubleshooting

If `/developer-portal` returns 404, check that the current deployment image includes `backend/app/static/developer_portal/` and that the router is included in `backend/app/main.py`. If the HTML loads but assets do not, check browser network requests to `/developer-portal/styles.css` and `/developer-portal/app.js`.

The live OpenAPI schema is the authority for route schemas, required fields and status codes.
