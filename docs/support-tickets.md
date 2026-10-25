# FinPilot Customer Support Tickets

## Capabilities

- Tenant-isolated ticket creation, viewing and tracking.
- Category values: `API_ISSUE`, `INTEGRATION_PROBLEM`, `SYSTEM_ERROR`, `CONFIGURATION_REQUEST`, `USER_ACCESS_REQUEST`, `REPORTING_REQUEST`, `OTHER`.
- Priorities: `LOW`, `MEDIUM`, `HIGH`, `URGENT`.
- Statuses: `OPEN`, `ASSIGNED`, `IN_PROGRESS`, `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`.
- Active-user assignment, comments, staff-only internal notes, file attachments, and append-only event history.
- `resolution_time_seconds` is calculated from `created_at` to the current `resolved_at`. It is `null` while unresolved. Reopening a resolved/closed ticket clears the current `resolved_at`; earlier resolution/status events remain in history.
- Ticket uploads use the configured storage abstraction and enforce `ALLOWED_FILE_TYPES` and `MAX_FILE_SIZE`. File downloads return attachment disposition, `nosniff`, and private/no-store cache headers.

## Access model

Normal authenticated users can create tickets and access only tickets they created. Tenant administrators, organization administrators and Customer Success Managers can manage tickets within their own tenant. A `Support Agent` is a platform support role: agents can list and manage customer tickets across tenants, but the cross-tenant query path is explicitly opted out of the generic tenant filter and is only selected for that role. Agent writes temporarily switch the session tenant context to the authorized ticket's tenant for the transaction, then restore the actor's tenant. Agents can assign tickets only to active Support Agents in the support team's tenant; other tenant staff can assign only users in the ticket's tenant.

Comments are public by default. Only staff can create internal notes, and non-staff comment listing excludes them. Attachments are accessed only after ticket-level visibility is verified; knowing an attachment UUID alone does not authorize a download.

## Routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/support/tickets` | Create a ticket |
| GET | `/api/v1/support/tickets` | List visible tickets; supports `status`, `category`, `priority`, `assigned_to`; Support Agents may also filter by `tenant_id` |
| GET | `/api/v1/support/tickets/{ticket_id}` | Get a ticket |
| PATCH | `/api/v1/support/tickets/{ticket_id}/assignment` | Assign or unassign (staff only) |
| PATCH | `/api/v1/support/tickets/{ticket_id}/status` | Status transition (staff only) |
| POST / GET | `/api/v1/support/tickets/{ticket_id}/comments` | Add/list visible comments |
| GET | `/api/v1/support/tickets/{ticket_id}/history` | Read status/assignment/activity events |
| POST / GET | `/api/v1/support/tickets/{ticket_id}/attachments` | Upload/list attachments |
| GET | `/api/v1/support/tickets/{ticket_id}/attachments/{attachment_id}/download` | Authorized file download |

## Example ticket payload

```json
{
  "title": "API requests return errors",
  "description": "Requests to /api/v1/transactions fail with HTTP 500.",
  "category": "API_ISSUE",
  "priority": "HIGH"
}
```

## Status transitions

- `OPEN` → `ASSIGNED`, `IN_PROGRESS`, `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`
- `ASSIGNED` → `OPEN`, `IN_PROGRESS`, `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`
- `IN_PROGRESS` → `OPEN`, `ASSIGNED`, `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`
- `WAITING_CUSTOMER` → `OPEN`, `ASSIGNED`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`
- `RESOLVED` → `OPEN`, `ASSIGNED`, `IN_PROGRESS`, `CLOSED`
- `CLOSED` → `OPEN` (reopen)

## Apply and verify

1. Add `SUPPORT_AGENT = "Support Agent"` to `UserRole` in `backend/app/utils/enums.py`. The `users.role` column is a string, so this does not require a database enum migration.
2. Apply the snippets under `integration-snippets/` to `backend/app/main.py`, `backend/app/models/__init__.py`, and `backend/alembic/env.py`.
3. Confirm that the currently applied migration head is `d9e4a8b7c612` or update `down_revision` if your branch differs. Run `uv run alembic upgrade head` from `backend/`.
4. Run `uv run pytest tests/integration/test_support_tickets.py` from `backend/`.
5. Check `ALLOWED_FILE_TYPES`, `MAX_FILE_SIZE`, and `STORAGE_PATH` in your existing settings/environment. Do not broaden the existing allowed MIME types without a security review.

The migration creates four tables and uses composite foreign keys from comments, attachments and history to `(ticket_id, tenant_id)`, preventing a child record from being attached to a ticket under a different tenant. It stores ticket attachment bytes through the configured storage service; database backup procedures do not automatically guarantee backup of the separate file-storage volume, so include that volume in disaster-recovery backups.
