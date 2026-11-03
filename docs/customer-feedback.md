# Customer feedback and product roadmap

## Overview

The customer-feedback API accepts structured feedback from an authenticated user, tracks status and priority, records a history timeline, and supports a product-team roadmap view. Feedback records are owned by the submitting user's tenant. The shared product roadmap supports public and internal visibility.

## Routes

Base path: `/api/v1/customer-feedback`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/` | Submit feedback for the current tenant |
| GET | `/` | List current-tenant feedback (optional status, limit) |
| GET | `/summary` | Current-tenant feedback summary |
| GET | `/roadmap` | List public roadmap items |
| GET | `/{feedback_id}` | Read one current-tenant feedback item |
| GET | `/{feedback_id}/history` | Read the current-tenant feedback timeline |
| GET | `/product` | Product-team cross-tenant feedback list and filters |
| GET | `/product/summary` | Product-team aggregate summary |
| GET | `/product/roadmap` | Product-team public and internal roadmap |
| POST | `/product/roadmap` | Create a roadmap item |
| PATCH | `/product/roadmap/{roadmap_item_id}` | Change roadmap status, visibility or release target |
| PATCH | `/product/{feedback_id}` | Triage feedback, set priority/status, link roadmap item |
| GET | `/product/{feedback_id}/history` | Read feedback history as product team |

Check the live OpenAPI schema at `/docs` for request fields, response envelopes and exact query parameters.

## Customer submission

Categories:
- `FEATURE_REQUEST`
- `IMPROVEMENT`
- `PROBLEM`
- `COMPLAINT`

A new submission starts with `SUBMITTED` status and `MEDIUM` priority. Valid statuses are `SUBMITTED`, `UNDER_REVIEW`, `ACCEPTED`, `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `DECLINED` and `DUPLICATE`. Priorities are `LOW`, `MEDIUM`, `HIGH` and `CRITICAL`.

## Triage guide

1. Move new submissions into `UNDER_REVIEW` and assess customer impact, frequency, severity and strategic fit.
2. Assign a priority supported by a short rationale.
3. Accepted requests can move through `PLANNED`, `IN_PROGRESS` and `COMPLETED`; unsupported items should be marked `DECLINED`; duplicates should be linked to or documented against a canonical request.
4. Link roadmap items where useful. Keep roadmap items `INTERNAL` until cleared for customer visibility.
5. Review `GET /product/summary` and tenant summaries to monitor volumes, triage backlog, high/critical items, progress and roadmap linkage.

## Access and privacy

- Customer operations use the authenticated user's tenant; the create schema does not allow the caller to choose a tenant.
- Customer reads and history are tenant-scoped. A cross-tenant ID must not disclose another tenant's feedback.
- Product-wide operations require both the Product Manager role and trusted `is_platform_admin=True`; the role label alone is insufficient.
- Customer roadmap queries expose only public items.
- Internal roadmap titles and identifiers must not leak into customer-facing feedback responses.
- The timeline should only be read after the associated feedback record has passed its access check.

## Implementation and verification

The active router is `backend/app/api/customer_feedback.py`, registered by `backend/app/main.py`. Models, schemas, repositories and services are under `backend/app/`. The schema migration is `backend/alembic/versions/b2f70c1d8e43_customer_feedback.py`.

From `backend/`, inspect the current revision graph and apply pending migrations using:

```bash
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run pytest tests/integration/test_customer_feedback.py -q
```

Use the current migration graph, not a hard-coded revision from an older feature branch. Use a dedicated PostgreSQL test database. Verify submission, filtering, triage, roadmap visibility, history and cross-tenant denial. Do not use real customer data.
