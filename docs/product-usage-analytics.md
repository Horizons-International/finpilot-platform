# Product usage analytics

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/product-analytics/dashboard` | Customer-level usage KPIs and feature adoption |
| GET | `/api/v1/product-analytics/features` | Aggregate most-used and unused feature report |

Both endpoints accept inclusive `start_date` and `end_date` ISO dates plus an optional `tenant_id`. Reports default to the previous 30 calendar days (including today) and reject ranges longer than 367 calendar days.

## Access model

All supported customer-facing roles can view their own tenant's usage. Cross-tenant analysis requires the existing trusted `is_platform_admin=True` claim. A `UserRole.PRODUCT_MANAGER` label alone is insufficient, so tenant-level role assignment cannot grant cross-tenant visibility. Normal tenant users cannot select another tenant. Deliberate cross-tenant SQLAlchemy queries include `skip_tenant_filter=True` with a reason and restrict the target tenant when a filter is supplied.

## Data sources

- `security_events`: request routes and tenant/user IDs for feature use, active-user estimates, and API calls.
- `audit_logs`: successful logins.
- `identity_verification_cases`: verification requests created.
- `ai_usage_logs`: AI usage records.
- `workflow_executions`: workflow runs started.
- `report_exports`: report export requests.

## Feature classifications

Known routes are categorized as customer management, verification, AI services, workflows, reporting, document management, integrations, support, developer platform, customer success, or risk monitoring. The service reports the request count for each category, top five used features, and categories with no recorded requests during the selected period. Raw URLs and IDs are not returned in the report.

## Operational notes

This implementation does not duplicate the request stream into a second table. Counts reflect the event retention and completeness of existing security/audit records. If analytics retention must exceed the retention of those records, add a scheduled daily snapshot into the existing `app.analytics` aggregation framework as a later optimization rather than synchronously writing a second row on every request.
