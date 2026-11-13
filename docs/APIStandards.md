# API standards

## API framework and route organization

- The active HTTP application is FastAPI in `backend/app/main.py`.
- Business routes are grouped into router modules under `backend/app/api/`.
- Versioned product routes use the `/api/v1` prefix; use the running OpenAPI schema to discover the exact route set.
- Request and response contracts belong in Pydantic schemas under `backend/app/schemas/` or the relevant feature package, not inline in route handlers unless intentionally small.

## Request handling

1. Validate inputs at the API boundary with Pydantic.
2. Resolve the authenticated principal and authorization dependencies before domain work.
3. Establish tenant context from trusted identity/session data; do not trust a client-provided tenant ID as an authorization decision.
4. Delegate business rules and orchestration to a service.
5. Use repositories for persistence and query composition.
6. Return the documented response model and a meaningful HTTP status.

## Authentication and permissions

JWT-protected endpoints expect `Authorization: Bearer <access_token>`. Login and token refresh use the authentication routes. Some partner integration routes instead require `X-API-Key` and a specific API-key permission; this is endpoint-specific and must not be generalized to all routes.

Document role requirements, tenant scope and platform-admin requirements for each new route. A display role or request payload is not a trusted substitute for platform-admin claims established by the authentication layer.

## Errors and status codes

Use FastAPI/Pydantic validation and the project's existing error handling. Common HTTP semantics include 400 for invalid operations, 401 for missing/invalid authentication, 403 for authenticated but forbidden access, 404 for resources outside the caller's visible scope or missing resources, 409 for conflicts and 422 for schema validation. Do not expose stack traces, secrets, SQL text or sensitive document content in client responses.

The generated OpenAPI schema is authoritative for the actual response envelope and status codes in a deployed version.

## Pagination, filtering and ordering

Use the established pagination/filtering conventions within the relevant router/schema. Validate page sizes and date ranges. Ensure every filter is combined with tenant scope; a tenant filter is never allowed to widen the caller's access.

## API changes

- Prefer additive, backwards-compatible schema changes.
- Treat response fields, enum values, status transitions and error shapes as contracts.
- Do not silently repurpose a field.
- Update feature documentation, tests and OpenAPI descriptions with every behavior change.
- Add authorization, tenant-isolation and negative-path tests alongside happy-path tests.

## Documentation and verification

For every route group, document purpose, authentication mechanism, roles, tenant scope, request example, status transitions and expected error conditions. After changes, inspect `/openapi.json` from the running application and run the backend quality/test commands.
