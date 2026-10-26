# Customer Feedback Operations

## Triage guide

1. New customer submissions start at `SUBMITTED` with `MEDIUM` priority.
2. Product staff move submissions to `UNDER_REVIEW` and set priority based on customer impact, frequency, severity and strategic fit.
3. Accepted requests can move through `PLANNED`, `IN_PROGRESS`, and `COMPLETED`; unsupported requests should be marked `DECLINED`; duplicates should reference the product team's canonical request through notes/roadmap planning.
4. If related to a roadmap item, link it. Prefer `PUBLIC` visibility when customers may safely see the item; default new roadmap items to `INTERNAL` until they are ready to be shared.
5. Review `GET /product/summary` to monitor submissions, items awaiting triage, high/critical priority, work in progress, completed/declined requests and roadmap linkage.

## Security

- Customer endpoints use the authenticated user's tenant; clients cannot supply a `tenant_id` when creating feedback.
- A feedback ID from another tenant returns 404 from customer-scoped reads.
- Cross-tenant product review requires both `UserRole.PRODUCT_MANAGER` and `is_platform_admin=True`.
- Internal roadmap items are never listed in the customer roadmap and their titles are omitted from customer feedback responses.
- The timeline is queryable only after verifying access to the associated feedback item.
