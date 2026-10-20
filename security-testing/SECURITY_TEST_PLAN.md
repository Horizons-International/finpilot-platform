# FinPilot Security Test Plan

## Objective

Prepare FinPilot for a bank/customer security review by providing repeatable tests and an auditable route from finding discovery through remediation and retest.

## Scope

**Included:** authentication boundaries; authorization checks; request-schema validation; API security headers; basic rate-limit enforcement; Python static analysis; Python dependency advisory audit; test environment isolation; finding tracking.

**Required manual follow-up:** role-based authorization, object-level authorization (IDOR/BOLA), cross-tenant isolation, MFA/session lifecycle, password reset/invitation flows, exports and file access, API-key permissions, webhook/SSRF controls, error/log disclosure, TLS/ingress configuration, secrets, container/image vulnerabilities, database and network configuration, and business-logic abuse cases.

**Out of scope unless separately approved:** production systems, real customer data, destructive tests, denial-of-service testing, social engineering, third-party systems, and active automated scanning beyond the local test stack.

## Roles

- **Assessment lead:** confirms written authorization, scope, test window, exclusions, contacts, and stop conditions.
- **Tester:** executes checklist items and records reproducible evidence.
- **Service owner:** owns code changes and remediation.
- **Security reviewer:** triages severity, reviews risk acceptance, and approves retest/closure.
- **Bank/compliance stakeholder:** approves policy-sensitive exceptions and residual-risk acceptance where applicable.

## Test cases

| ID | Area | Test | Expected outcome | Evidence |
|---|---|---|---|---|
| ST-001 | API | `GET /health` response hardening | Required API security headers and request ID exist | JUnit report and headers |
| ST-002 | Authorization | Anonymous `GET /api/v1/auth/admin-only` | `401 Unauthorized`; no protected data returned | Status and response body |
| ST-003 | Authorization | Anonymous `GET /api/v1/security/events` | `401 Unauthorized`; security events are not exposed | Status and response body |
| ST-004 | Input validation | Malformed email/too-short password to login schema | `422 Unprocessable Entity`; handler does not attempt authentication | Status and safe response sample |
| ST-005 | Rate limiting | Four requests to an otherwise nonexistent local probe route with lab threshold three | First three `404`, next `429` and `Retry-After` | JUnit report and response headers |
| ST-006 | Source | Bandit scan of `backend/app` | Results reviewed; unexplained high-severity results are not accepted | Bandit JSON report |
| ST-007 | Dependencies | `pip-audit` on backend resolved environment | Known advisories reviewed and tracked | pip-audit JSON report |
| ST-008 | Access control | Two users with different roles attempt a documented privileged action | Least privilege enforced (expected `401`/`403` as applicable) | Account roles, endpoint, status |
| ST-009 | Tenant isolation | Tenant A requests Tenant B's known test-object ID using Tenant A credentials | No cross-tenant data leak; normally `404` or `403` by endpoint contract | Request/response, test tenant IDs |
| ST-010 | Infrastructure | Review Compose, TLS, secrets, open ports, image versions, and runtime privileges | Deviations documented and tracked | Config review record and scanner outputs |

ST-008 through ST-010 require controlled fixtures and human review; the supplied automatic suite does not mark them passed by default.

## Environment controls

1. Use `docker/docker-compose.security-test.yml` only for this task; it is isolated from the regular compose project and does not import the normal `.env`.
2. Confirm the published ports bind to `127.0.0.1` only.
3. Use synthetic records and test credentials only.
4. Confirm migrations complete and `/health` is available before running the tests.
5. Avoid running production, stress, fuzzing, destructive, or state-changing tests without a separate signed scope and recovery plan.
6. Save reports to `security-testing/results/`; redact tokens, credentials, customer information, and secrets from evidence.

## Reporting

Each finding should have a unique ID, severity and rationale, affected assets, preconditions, reproducible steps, sanitized request/response evidence, business impact, remediation recommendation, owner, target date, status, fix reference, retest result, and residual-risk decision. A scan with zero findings is not proof of security.
