# Billing data model and operational rules

## Source of usage data

`SubscriptionUsageCounter` remains FinPilot's metering source. The billing service reads `api_calls`, `verification_checks`, and `ai_requests` by the existing monthly `period_start`. It never increments, clears, or recreates counters. Usage values are summed across the invoice's full calendar months.

Included units are separate from `limits`: `limits` enforce product capacity/quota through the existing subscription services; `included_units` are the quantity per metric per calendar month that is included in the commercial fee before a rate is applied.

## Pricing rules

- `SUBSCRIPTION` supports `MONTHLY` or `ANNUAL`, with `base_fee` charged once per invoice period and no usage rates.
- `USAGE_BASED` requires `MONTHLY` and one or more unit rates. A monthly `base_fee` is optional. Rates are available for `api_calls`, `verification_checks`, and `ai_requests`.
- `ENTERPRISE` supports `MONTHLY`, `ANNUAL`, or `CUSTOM`; it needs a positive base fee or at least one unit rate. A custom base fee is charged once for the whole requested custom period.
- Price terms cannot be edited in place while a plan has active assignments. Create a new plan and reassign customers to make a price change explicit; existing invoices remain immutable snapshots.
- Rate values are kept as decimal strings in JSON and calculated with Python `Decimal`; each line total is rounded to cents using half-up rounding.
- For a period spanning several months, each month's included units are applied separately before billable quantities are added together.

## Plan assignment

`POST /api/v1/billing/assignments` creates a new subscription row with `billing_plan_id`, plan quota limits and enabled features. A prior current/trial subscription is marked cancelled (or expired if its end date passed); prior rows and invoices are retained for history. Start dates must be the first day of a calendar month and end dates the last day of a month, matching the granularity of current usage counters.

## Invoice integrity and lifecycle

`POST /api/v1/billing/invoices/generate` generates a `DRAFT` invoice. The invoice header snapshots the plan name and currency; each line stores its description, metric, quantity, unit price and amount. Updating a billing plan therefore does not change previously generated invoice amounts. A unique key prevents more than one invoice per tenant and calendar period; repeated generation requests return the existing invoice snapshot.

Allowed status transitions are `DRAFT → ISSUED → PAID`, with `DRAFT → VOID` or `ISSUED → VOID` also supported. `PAID` and `VOID` are terminal. Overdue state is exposed as `is_overdue` when an invoice is still `ISSUED` and its due date has passed; it is not a separate persisted status.

Tenant invoice reads are limited to the current tenant and are restricted to tenant administrators/auditors or trusted platform administrators. Plan management, cross-tenant assignment, invoice generation, and status changes require the trusted `is_platform_admin` guard.

## Scope boundaries

This is the foundational commercial ledger only. It does not process payments, charge a card/bank account, calculate tax/VAT, handle discounts/credits, deliver invoice PDFs/emails, or connect to accounting software. These should be separate integrations built on the immutable invoice snapshots.
