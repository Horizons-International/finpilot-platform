# FinPilot Customer Success API

Base path: `/api/v1/customer-success`. All endpoints require a FinPilot access token and the dedicated `Customer Success Manager` role. Keep this role limited to trusted customer-success staff because the usage-import operation reads metrics for the customer tenant explicitly associated with a profile.

## Data model and tenant boundaries

A profile represents the relationship between a customer-success team's tenant (`tenant_id`) and an enterprise customer tenant (`customer_tenant_id`). The target bank's production `Customer` rows are not copied or modified. The owner tenant is automatically taken from the authenticated request; clients cannot provide `tenant_id` in payloads. Profiles, usage snapshots, support interactions, and relationship history are tenant-scoped. Composite database foreign keys prevent a child record from referencing a profile in another owner tenant.

A team may create only one profile per customer tenant. Duplicate profile or duplicate usage period requests return a conflict. Profile IDs belonging to another team's tenant are intentionally returned as 404.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/customer-success/summary` | Account count by health band and churned count |
| `GET` | `/api/v1/customer-success` | List profiles; optional `account_status`, `health_band`, and `assigned_manager_id` filters |
| `POST` | `/api/v1/customer-success` | Create a profile for a known `customer_tenant_id` |
| `GET` | `/api/v1/customer-success/{profile_id}` | Read account status, stage, owner, health score and plan |
| `PATCH` | `/api/v1/customer-success/{profile_id}` | Change status, implementation stage, manager, success plan or contact date |
| `POST` | `/{profile_id}/usage-snapshots` | Record usage metrics for a unique period start |
| `POST` | `/{profile_id}/usage-snapshots/from-subscription` | Import current-month API-call, active-user, and quota usage for the linked customer tenant |
| `GET` | `/{profile_id}/usage-snapshots` | Read past usage snapshots |
| `POST` | `/{profile_id}/support-interactions` | Record support ticket / interaction |
| `GET` | `/{profile_id}/support-interactions` | Read support history |
| `PATCH` | `/{profile_id}/support-interactions/{interaction_id}` | Update ticket status, severity, assignee, resolution notes |
| `GET` | `/{profile_id}/history` | Read append-only relationship timeline |
| `POST` | `/{profile_id}/notes` | Append an immutable relationship note |
| `POST` | `/{profile_id}/recalculate-health` | Recalculate score and record a timeline event |

## Example: create a profile

```bash
curl -X POST "http://localhost:8000/api/v1/customer-success" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_tenant_id": "00000000-0000-0000-0000-000000000000",
    "account_status": "TRIAL",
    "implementation_stage": "CONFIGURATION",
    "assigned_manager_id": null,
    "success_plan": "Complete API integration, training and UAT."
  }'
```

Replace the UUID with a real enterprise tenant ID visible to the authorized customer-success team. The zero UUID above is illustrative only.

## Example: record usage

```bash
curl -X POST "http://localhost:8000/api/v1/customer-success/$PROFILE_ID/usage-snapshots" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "period_start": "2026-10-01",
    "period_end": "2026-10-31",
    "active_users": 70,
    "licensed_users": 100,
    "api_calls": 76000,
    "api_call_limit": 100000,
    "active_features": 7,
    "available_features": 10,
    "source": "API_REPORT"
  }'
```

Snapshots are immutable measurement records. You can submit manually aggregated metrics, or call `POST /api/v1/customer-success/{profile_id}/usage-snapshots/from-subscription` to import the current month's API-call counter, active-user count and subscription limits from the single customer tenant linked to that profile. That operation uses explicit tenant predicates plus a documented `skip_tenant_filter` reason; it never accepts an arbitrary target tenant ID. It does not modify billing counters. Feature-adoption metrics are left at zero/unavailable by this importer because FinPilot's subscription counters do not provide a reliable product-feature engagement measure yet.

## Example: import current-month subscription usage

```bash
curl -X POST "http://localhost:8000/api/v1/customer-success/$PROFILE_ID/usage-snapshots/from-subscription" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Only a customer tenant with an active or trial subscription can be imported. Each profile allows one snapshot per `period_start`; if a manual snapshot already exists for the current month, the importer returns `409` rather than overwriting historical data.

## Example: track a support issue

```bash
curl -X POST "http://localhost:8000/api/v1/customer-success/$PROFILE_ID/support-interactions" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Integration callback is failing",
    "description": "Customer reports HTTP 5xx responses from their callback receiver.",
    "category": "INTEGRATION",
    "severity": "HIGH",
    "status": "OPEN",
    "assigned_to": null
  }'
```

A support interaction contributes to the score until its status is `RESOLVED` or `CLOSED`. Transitioning to a resolved/closed status stamps `resolved_at`; reopening clears it.

## Health score method

The score is deterministic and bounded to 0–100. It starts at 100, then subtracts the documented penalties below:

- Account status: `AT_RISK` −20, `PAUSED` −25, `CHURNED` −50; `TRIAL` and `ACTIVE` have no direct penalty.
- Implementation stage: `NOT_STARTED` −20, `CONFIGURATION` −15, `INTEGRATION` −10, `TESTING` −5, `READY_FOR_PRODUCTION` −2, `LIVE` −0.
- Latest usage sample: active-user adoption below 25% −20, below 50% −12, below 75% −6; feature adoption below 25% −10 or below 50% −5. When an API call limit is present, zero calls penalize 8, utilization below 5% penalizes 5, and utilization at or above 95% penalizes 5. A usage sample more than 90 days old penalizes 5. No sample yet penalizes 5 to make missing instrumentation visible.
- Open support: only the most severe active interaction counts, preventing a ticket backlog from linearly exhausting the score; `LOW` −3, `MEDIUM` −8, `HIGH` −15, `CRITICAL` −25.
- Contact recency: no recorded contact −5; older than 30 days −5, older than 60 days −10, older than 90 days −15.

After penalties, the score is clipped to 0–100. `HEALTHY` is 80–100, `NEEDS_ATTENTION` is 60–79, and `AT_RISK` is below 60. Scores recalculate when a profile, usage snapshot, or support interaction changes, and can be recalculated on demand. This is an explainable operational heuristic, not an automated credit, compliance or regulatory decision. Tune its weights against real customer-success outcomes before using it for automated decisions.

## Status values

- Account: `TRIAL`, `ACTIVE`, `AT_RISK`, `PAUSED`, `CHURNED`.
- Implementation stage: `NOT_STARTED`, `CONFIGURATION`, `INTEGRATION`, `TESTING`, `READY_FOR_PRODUCTION`, `LIVE`.
- Support category: `INCIDENT`, `QUESTION`, `REQUEST`, `BILLING`, `INTEGRATION`, `TRAINING`, `OTHER`.
- Support severity: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- Support status: `OPEN`, `IN_PROGRESS`, `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`.

## Timeline and errors

Profile changes, assignment, contact records, usage snapshots, support changes, notes, and score changes append events to `customer_success_history`. Do not update or delete timeline rows from API routes. Standard FinPilot error envelopes are used. Expected statuses include `201` for create, `200` for read/update, `404` for missing or out-of-scope IDs, `409` for duplicate profile/snapshot, `422` for invalid fields and `401/403` for authentication/authorization failures.
