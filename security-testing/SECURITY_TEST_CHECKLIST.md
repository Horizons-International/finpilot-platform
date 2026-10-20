# Security Assessment Checklist

Use `- [ ]` until the check has actually been run. For every completed item, record tester, date, outcome, and evidence path/link. A checked box without evidence is not assessment evidence.

## Assessment authorization and preparation

- [ ] Written authorization identifies system owner, approved hostnames/IPs, environment, dates, source IPs, allowed methods, third-party exclusions, and emergency contacts.
- [ ] Stop conditions, incident escalation path, data handling, and test window are agreed.
- [ ] Test environment uses synthetic data, isolated credentials, and a recoverable database snapshot.
- [ ] Accounts are prepared for anonymous, ordinary user, organization admin, platform admin, disabled user, and two separate tenants as applicable.
- [ ] All evidence is sanitized; no live tokens, passwords, keys, or customer identifiers are placed in reports.
- [ ] OpenAPI route inventory, role matrix, tenant ownership rules, data-flow diagrams, and asset inventory are current.

## Application: authentication and session handling

- [ ] Missing, malformed, tampered, expired, and wrong-type access tokens are rejected.
- [ ] Refresh tokens cannot be used as access tokens; revoked/expired sessions cannot be revived.
- [ ] Invalid credentials produce a non-enumerating response appropriate to the API contract.
- [ ] Login failure monitoring/lockout controls and route/IP rate limits behave as configured.
- [ ] MFA enrollment, confirmation, disablement, recovery, and sensitive actions require appropriate proof.
- [ ] Password change/reset/invitation workflows enforce expiry, one-time use, current-password/MFA rules as designed.
- [ ] Logout and session revocation invalidate access according to the documented implementation.
- [ ] Tokens, passwords, MFA codes, reset tokens, API keys, and sensitive payloads are not logged.

## Application: authorization and input validation

- [ ] Anonymous users cannot access protected routes.
- [ ] A low-privilege user cannot execute admin/organization-admin operations.
- [ ] Resource/object IDs from another user or tenant cannot be read, modified, exported, or deleted (BOLA/IDOR).
- [ ] Tenant filtering is verified for lists, detail views, nested resources, reports, exports, files, AI interactions, and background jobs.
- [ ] Mass-assignment attempts cannot alter tenant IDs, roles, ownership, status, or privileged flags.
- [ ] Invalid types, missing fields, oversized values, malformed UUIDs, Unicode edge cases, and boundary values are rejected safely.
- [ ] SQL/ORM injection strings are treated as data; template/command/path traversal payloads are tested only in the authorized lab.
- [ ] File upload type/size/content handling, storage path boundaries, download permissions, and archive extraction are reviewed.
- [ ] Exceptions do not leak stack traces, SQL details, secrets, internal paths, or provider responses.

## API security and rate limits

- [ ] Security headers and request ID are present on API responses; production TLS/HSTS policy is separately verified.
- [ ] Rate limiting is exercised on ordinary routes and sensitive routes, and `429`/`Retry-After` behavior is documented.
- [ ] Request body-size limits and validation failure logging work without logging sensitive body content.
- [ ] CORS is restrictive and appropriate; preflight/credential behavior is reviewed.
- [ ] HTTP methods, content types, pagination, sorting, filtering, and export parameters cannot bypass validation or permissions.
- [ ] OpenAPI/Swagger/ReDoc exposure in production follows bank policy; internal/admin endpoints are not accidentally documented as public.
- [ ] API-key creation, scope enforcement, expiry/revocation, and tenant binding are tested if enabled.
- [ ] Webhooks validate signatures/replay protection and do not permit unapproved SSRF targets or redirects.
- [ ] Authentication and access denials create useful audit events without sensitive values.

## Infrastructure, configuration, and dependencies

- [ ] `.env`, tokens, signing keys, encryption keys, and test passwords are not committed or embedded in images/logs.
- [ ] Production `SECRET_KEY`, `ADMIN_PASSWORD`, `DATA_PROTECTION_KEY`, and webhook keys use approved secret management and rotation.
- [ ] Database TLS, ingress TLS, trusted proxy headers, secure transport, and exposed ports are reviewed.
- [ ] Docker images/dependencies are pinned or refreshed according to policy; containers use least privilege and minimal permissions.
- [ ] Dependency advisory scan (`pip-audit`) is run against the resolved backend environment and exceptions are documented.
- [ ] Python static security analysis (`Bandit`) is run; high-confidence findings are triaged.
- [ ] Container image/base-image and IaC/Compose scans are planned or executed with approved tools.
- [ ] Database users have least privilege; test and production credentials/volumes are separate.
- [ ] Debug endpoints, profiling, dev reload, development admin tools, default credentials, and unintended management ports are disabled or restricted in production.
- [ ] Backups, restore procedure, log retention, alerting, incident response, and evidence access controls are confirmed.

## Findings and closure

- [ ] Every finding has a unique ID in `VULNERABILITY_REGISTER.csv`.
- [ ] Severity, exploitability, impact, affected tenants/data, and remediation owner are recorded.
- [ ] Fixes are linked to a commit/PR and have a regression test where feasible.
- [ ] Retest uses the original reproduction steps and records pass/fail evidence.
- [ ] Accepted risk has written approval, rationale, expiry/review date, and compensating controls.
- [ ] Final summary includes scope, dates, tools/versions, results, exclusions, unresolved risks, and reviewer approval.
