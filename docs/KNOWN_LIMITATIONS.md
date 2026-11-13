# Known limitations and production-readiness notes

This document intentionally distinguishes code paths that exist from capabilities that require external integrations, operational configuration, independent evidence or further implementation. It is not a vulnerability report or a certification.

## Product scope

- The active application is the FastAPI backend under `backend/app/`.
- The root `frontend/` and `mobile/` directories contain README placeholders only; no complete customer-facing web or mobile application is delivered here.
- API consumers use REST endpoints and the generated OpenAPI schema. A developer portal is included as a backend-served browser tool; it is not a replacement for a full product frontend.

## External providers

The checked-in backend environment template selects mock providers for AI, verification, OCR, document extraction, email and SMS. The local flows can therefore be exercised without live provider credentials, but the use of a mock adapter is not evidence of successful real-provider integration.

Before production, select supported providers, configure credentials and timeouts, test error/retry behavior, review data processing terms, and verify that sensitive customer/document data is handled under the institution's policies.

## Sandbox boundaries

The sandbox uses separate synthetic `sandbox_*` records and prefixed test API keys. Its webhook simulator returns a stored synthetic payload with `SIMULATED_NOT_SENT`; it deliberately does not issue outbound HTTP requests. The sandbox guide advises a separate host/process, database, credentials and storage from production. Review [sandbox-api.md](sandbox-api.md).

## Billing boundaries

The billing module provides plans, subscription assignments, usage-based calculations and immutable invoice snapshots. It does not charge cards or bank accounts, settle payments, calculate taxes/VAT, apply discounts/credits, send invoice PDFs/emails or integrate with accounting software. See [billing.md](billing.md).

## Rate limiting and scaling

The application-level rate limiter is process-local. In a multi-replica or multi-worker deployment, each process can maintain its own limit state; this is not a shared quota service. Production should enforce distributed controls at a trusted gateway/WAF or move the limiter to a shared atomic backend. Forwarded client-IP headers must be accepted only from explicitly trusted proxies.

## High availability

The development Compose file starts multiple API containers behind HAProxy, but they still share a host and supporting services. This is useful for local balancing/failover experiments, not infrastructure-level high availability. Production resilience requires independent hosts/failure domains, database HA, shared durable storage, backups, monitoring and operational failover drills.

## Database and file storage

The database and file store are separate persistence domains. Database backups alone do not guarantee recovery of uploaded files. Ensure the configured storage path/volume is captured by the backup plan and verify a complete restore of both database and files.

The migration history requires PostgreSQL with the server-side pgvector extension. Installing the Python package does not install the extension into PostgreSQL. Use the provided pgvector image or a database installation with the extension available.

## Security posture

The code includes authentication, authorization, tenant-aware access patterns, audit/security event recording and additional HTTP controls. These mechanisms still require threat modeling, role/tenant regression testing, penetration testing, secure deployment configuration, secret rotation, monitoring and incident-response procedures.

A critical repository hygiene issue was observed during the documentation review: **`docker/.env` is tracked in the current Git tree despite environment files being listed in `.gitignore`.** Its contents were not read or copied into documentation. Before sharing this repository:
1. Privately inspect the file and all relevant historical versions.
2. Remove real secrets from tracked content and Git history using an approved history-rewrite procedure if needed.
3. Rotate all credentials and keys that may have been committed.
4. Replace the tracked file with a safe `.env.example` template.
5. Re-run secret scanning against the current tree and full history.

Removing a secret from the latest tree is not sufficient if it remains in Git history or existing clones.

## Evidence versus implementation

The repository contains security and performance plans, test harnesses, CI workflows, backup scripts and runbooks. These are useful engineering assets but do not, by themselves, prove that the corresponding test or operational control passed recently. An evaluator should request/check evidence tied to the reviewed commit, environment and date.

Do not describe FinPilot as certified, independently penetration-tested, regulator-approved, production-proven or capacity-validated unless current authoritative evidence exists outside this documentation set.

## Items to validate before production

- Secret management, key rotation, TLS termination, database TLS and trusted proxy configuration.
- Distributed rate limits and abuse protection across replicas.
- Database capacity, connection pool sizing, backup retention, PITR and restore drills.
- Object/file storage encryption, access isolation, malware scanning, retention and deletion lifecycle.
- Real provider integration reliability, privacy, retry, cost and timeout behavior.
- Queue/worker concurrency, idempotency, retry exhaustion and observability.
- Tenant isolation and platform-admin escape hatches through independent tests.
- Security assessment, findings remediation and operational incident response.
- Regulatory/legal assessment for each target jurisdiction and institution.
