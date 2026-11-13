# FinPilot customer support tickets

## Capabilities

- Tenant-isolated ticket creation, viewing and tracking.
- Categories: `API_ISSUE`, `INTEGRATION_PROBLEM`, `SYSTEM_ERROR`, `CONFIGURATION_REQUEST`, `USER_ACCESS_REQUEST`, `REPORTING_REQUEST`, `OTHER`.
- Priorities: `LOW`, `MEDIUM`, `HIGH`, `URGENT`.
- Statuses: `OPEN`, `ASSIGNED`, `IN_PROGRESS`, `WAITING_CUSTOMER`, `RESOLVED`, `CLOSED`.
- Staff assignment, public comments, staff-only internal notes, file attachments and append-only event history.
- `resolution_time_seconds` is calculated from creation to the current resolution timestamp. It is null while unresolved. Reopening a resolved/closed ticket clears the current resolution timestamp; earlier events remain in history.
- Uploads use the configured storage abstraction and enforce the file-size and allowed-content-type settings. Downloads set attachment disposition, `nosniff` and private/no-store cache headers.

## Access model

Normal authenticated users can create tickets and access tickets they created. Tenant administrators, organization administrators and Customer Success Managers can manage tickets within their tenant. Support Agents can list/manage support tickets across tenants through a dedicated support-agent path. That privileged path must remain limited to the Support Agent role.

Support-agent writes temporarily bind session tenant context to the ticket tenant during the authorized operation and restore the actor's original tenant context. Agents may assign only to active Support Agents in the support team's tenant; other tenant staff may assign only users in the ticket's tenant.

Comments are public by default. Only staff can create internal notes, and non-staff listing excludes those notes. Attachment access verifies ticket visibility; knowing an attachment UUID is not sufficient for download.

## Routes

Base path: `/api/v1/support/tickets`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/` | Create a ticket |
| GET | `/` | List tickets visible to the current user; supports status, category, priority and assignee filters; tenant filter is for Support Agents |
| GET | `/{ticket_id}` | Retrieve one visible ticket |
| PATCH | `/{ticket_id}/assignment` | Assign or unassign (staff only) |
| PATCH | `/{ticket_id}/status` | Change status (staff only) |
| POST / GET | `/{ticket_id}/comments` | Add/list visible comments |
| GET | `/{ticket_id}/history` | Read status/assignment/activity events |
| POST / GET | `/{ticket_id}/attachments` | Upload/list attachments |
| GET | `/{ticket_id}/attachments/{attachment_id}/download` | Download an authorized attachment |

Example create body:

```json
{
  "title": "API requests return errors",
  "description": "Requests to a test endpoint fail with HTTP 500.",
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

The current repository already imports the support-ticket router from `backend/app/main.py`. Do not apply an old integration snippet or register the router a second time.

From `backend/`, inspect the actual migration graph and then apply pending migrations:

```bash
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run pytest tests/integration/test_support_tickets.py -q
```

The support-ticket migration file is `backend/alembic/versions/e2f1c4b8a907_support_ticket_module.py`. Its declared parent is a customer-success revision; never hard-code an assumed database head from an older branch. Let the repository's full migration graph and current Alembic state determine what is pending.

Check `ALLOWED_FILE_TYPES`, `MAX_FILE_SIZE_MB` and `STORAGE_PATH` in the active settings/environment. Do not broaden allowed MIME types without a security review. Include the physical file-storage volume in disaster-recovery backups; database backups alone do not recover uploaded bytes.

## Security checks for evaluation

Test normal customer ticket visibility, staff access within one tenant, support-agent access, internal-note redaction, unauthorized attachment download, cross-tenant ticket IDs and assignment restrictions. Confirm that all mutations create the expected history and do not leave the ORM session bound to the wrong tenant after the request completes.
