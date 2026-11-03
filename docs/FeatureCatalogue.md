# FinPilot feature catalogue

This catalogue maps high-level capabilities to implementation locations and documentation. The exact HTTP route inventory and schemas are generated from the running checkout at `/openapi.json`.

| Domain | Main implementation entry points | Guide |
|---|---|---|
| Authentication, users, profiles, invitations | `backend/app/api/auth.py`, `users.py`, `profile.py`; related services/repositories | [Backend README](../backend/README.md) |
| Tenant and organization administration | `backend/app/api/tenants.py`, `organizations.py` | [Architecture](Architecture.md) |
| Customer records, contacts, addresses, history | `backend/app/api/customers.py`, `customer_contacts.py`, `customer_addresses.py` | [Backend README](../backend/README.md) |
| Customer onboarding and verification | `customer_onboarding.py`, `verification_cases.py`, `verification_reviews.py`, `verification_case_assignments.py` | [Backend README](../backend/README.md) |
| Files, documents, OCR and extraction | `files.py`, `documents.py`, `ocr.py`, `extraction.py`, `document_review.py` | [OCR](ocr.md) |
| AML, transaction monitoring and risk | `aml_rules.py`, `transaction_monitoring.py`, `risk_scoring.py`, `risk_predictions.py`, `transaction_risk_analysis.py` | [Backend README](../backend/README.md) |
| Compliance cases, notes, priorities and analytics | `compliance_cases.py`, `investigation_notes.py`, `case_priorities.py`, `compliance_analytics.py` | [Backend README](../backend/README.md) |
| Tasks, workflow and SLA | `tasks.py`, `task_assignment_rules.py`; `backend/app/jobs/sla_monitor.py` | [Backend README](../backend/README.md) |
| Reports and asynchronous exports | `reports.py`, `report_exports.py`; `backend/app/jobs/report_export_worker.py` | [Backend README](../backend/README.md) |
| Analytics dashboards/metrics | `dashboard.py`, `customer_analytics.py`, `operations_analytics.py`, `executive_dashboard.py`, `metrics.py` | [Product usage analytics](product-usage-analytics.md) |
| API keys, integrations and webhooks | `api_keys.py`, `integrations.py`, `integration_management.py`, `webhooks.py` | [Developer portal](developer-portal/README.md) |
| Developer portal and sandbox | `developer_portal.py`, `sandbox.py` | [Sandbox API](sandbox-api.md) |
| Billing foundation | `billing.py`, subscription/usage models and services | [Billing](billing.md) |
| Customer success and support | `customer_success.py`, `support_tickets.py` | [Customer success](customer-success.md), [support](support-tickets.md) |
| Customer feedback and roadmap | `customer_feedback.py` | [Customer feedback](customer-feedback.md) |
| AI prompts, retrieval and assistant | `ai_assistant.py`, `ai_prompts.py`, `knowledge_documents.py`, `rag.py` | [AI framework](ai.md) |
| Data protection and audit | `data_protection.py`, `audit_events.py`, audit/security middleware and services | [Security baseline](../backend/SECURITY_BASELINE.md) |

## Important interpretation notes

- This is an orientation index, not a completeness or quality certification.
- A router file may expose multiple operations. Use live OpenAPI to enumerate them.
- Route access may differ by user role, tenant and trusted platform-admin state.
- Some provider integrations default to mock mode; confirm the selected provider and integration credentials before demonstrating external behavior.
- Read [Known Limitations](KNOWN_LIMITATIONS.md) for boundaries such as sandbox webhook simulation, billing scope and distributed rate limits.
