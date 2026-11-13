# FinPilot roadmap and status

This page summarizes the repository's current engineering scope as a review aid. It is not a promise of release dates or a product delivery commitment.

## Implemented code areas present in this repository

- Core FastAPI application, configuration, PostgreSQL persistence and Alembic migration history.
- JWT authentication, role/permission checks, user/profile operations, session controls and audit/security events.
- Multi-tenant foundations and tenant-aware business modules.
- Customer, onboarding, verification, document/file, AML/compliance and transaction-risk workflows.
- Tasks, assignment rules, workflows, SLA monitoring and notification/communication records.
- Reporting exports and multiple operational/business analytics modules.
- API keys, integration APIs, webhook subscription/delivery infrastructure, developer portal and synthetic sandbox.
- Billing foundations, customer success, support tickets, customer feedback and product usage analytics.
- AI prompt management, AI interaction history, knowledge documents, retrieval and assistant endpoints.
- Docker/HAProxy local topology, CI workflows, release automation, security/performance test tooling and disaster-recovery scripts.

Presence of code is not evidence that all features have passed full regression testing or are fully configured for production.

## Review and hardening priorities

1. **Repository secret hygiene:** remove any tracked runtime .env files, scan current tree and full Git history, rotate potentially exposed keys.
2. **Tenant isolation verification:** systematically test every tenant-owned resource, nested endpoint and platform-level bypass path.
3. **Production configuration:** external secret manager, TLS, trusted proxy, distributed rate limiting, database HA, durable file storage and monitoring.
4. **External provider acceptance:** configure and verify selected AI, identity, OCR, extraction, email and SMS provider adapters.
5. **Worker resilience:** define queue/locking semantics, idempotency, retry policies, dead-letter/alerting and duplicate-worker behavior.
6. **Independent security assurance:** threat model, penetration testing, remediation register and repeatable security regression.
7. **Performance/capacity evidence:** repeat load and stress tests using defined SLOs, production-like infrastructure and representative synthetic data.
8. **Recovery assurance:** backup and restore database plus uploaded files, verify RPO/RTO targets and test failover.
9. **Client applications:** implement and test web/mobile clients if those are in the product delivery scope.
10. **Commercial workflows:** implement payment collection, settlement, taxes, credits/discounts and accounting integrations if required.

## Evidence required to mark an area complete

For each item, retain the commit SHA, test report, environment, test data profile, observed results, reviewer and remediation status. Keep operational evidence (restore logs, performance reports, deployment approvals and provider acceptance tests) separate from source documentation.
