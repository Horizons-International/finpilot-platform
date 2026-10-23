# Self-service enterprise onboarding portal

## Overview

This feature extends FinPilot's existing platform-level `partner_onboarding` workflow to let a prospective bank begin onboarding before it has a tenant account. The existing `partner_onboarding` model is intentionally platform-level: `tenant_id` is created only when approval activates the bank. This avoids creating an invalid tenant-owned record before a tenant exists and preserves the existing platform-admin onboarding endpoints.

Portal-created requests get a high-entropy token. The API shows it only in the create response and stores only its SHA-256 hash. Send the token in `X-Onboarding-Token` on subsequent customer portal requests. It expires after 30 days. The calling portal must safely retain or securely deliver it.

## Customer workflow

1. Create the organization/onboarding request.
2. Complete or update company and contact information.
3. Nominate one or more first administrators.
4. Upload required business registration and regulatory license documents (optional supporting types are also supported).
5. Provide non-secret technical setup information, including sandbox/production target, HTTPS callback URL, optional allowed IP ranges, and integration contact.
6. Submit for internal review. The API rejects submission until business information, at least one administrator, and both required documents exist.
7. Platform staff assigns a reviewer and moves the request into compliance review.
8. Internal reviewers approve required documents. Stage transitions are checked server-side and cannot skip the required prerequisites.
9. Staff advances to technical setup and then API credentials. Activation is available only after the preceding requirements and administrator uniqueness checks pass.
10. The API credentials stage is followed by approval. To avoid issuing usable tenant credentials before activation is approved, the activation operation atomically creates the tenant and organization, materializes nominated admins as `UserInvitation` rows, creates an initial API key, and marks the onboarding ACTIVE. The progress view tracks credential issuance and activation as separate steps, but they complete in the same transaction. The raw API key is returned once only; the DB stores its SHA-256 hash.

## Customer portal endpoints

All endpoints are rooted at `/api/v1/partner-onboarding`.

| Method | Endpoint | Authentication / purpose |
|---|---|---|
| `POST` | `/portal` | Public submission; returns onboarding ID and one-time portal token |
| `GET` | `/portal/{id}/progress` | `X-Onboarding-Token`; view progress and submitted evidence metadata |
| `PATCH` | `/portal/{id}/business-information` | `X-Onboarding-Token`; update business information before compliance review |
| `POST` | `/portal/{id}/administrators` | `X-Onboarding-Token`; nominate an organization administrator; returns one-time invitation token |
| `POST` | `/portal/{id}/documents` | `X-Onboarding-Token`; multipart upload with `document_type` and `file` |
| `PUT` | `/portal/{id}/technical-setup` | `X-Onboarding-Token`; record integration setup metadata, never secret credentials |
| `POST` | `/portal/{id}/submit` | `X-Onboarding-Token`; validate required steps and submit the request for review |

### Create request example

```http
POST /api/v1/partner-onboarding/portal
Content-Type: application/json
```

```json
{
  "organization_name": "Example Bank",
  "legal_name": "Example Bank Limited",
  "registration_number": "REG-001",
  "tax_identification_number": "TAX-001",
  "industry": "Financial Services",
  "business_description": "A prospective regulated financial institution.",
  "contact_name": "Bank Integration Contact",
  "contact_email": "integration@example.com",
  "contact_phone": "+249912345678",
  "website": "https://example.com",
  "country": "SD"
}
```

The response contains `data.id` and `data.portal_token`. The token is a bearer credential: treat it as a secret. The response does not imply that the bank has been activated.

### Upload document example

Use `multipart/form-data` with `document_type` set to `business_registration` or `regulatory_license` and `file` containing a PDF, PNG, JPEG, or plain-text file permitted by the application configuration. The API enforces the configured maximum file size and basic content signatures for PDF, PNG, and JPEG uploads.

Other supported document types are `tax_certificate`, `authorized_signatory_list`, and `other`.

## Internal review endpoints

These routes require the existing platform-administrator authorization dependency:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/{id}/progress` | Internal progress view |
| `GET` | `/{id}/documents` | List evidence and its review state |
| `GET` | `/{id}/documents/{document_id}/download` | Download stored evidence |
| `PATCH` | `/{id}/documents/{document_id}/review` | Approve or reject evidence; notes required for rejection |
| `PATCH` | `/{id}/assignment` | Assign an active platform admin as reviewer |
| `POST` | `/{id}/advance` | Advance to the next required workflow stage |
| `POST` | `/{id}/approve` | Approve and activate; API key returned once for portal requests |
| `POST` | `/{id}/reject` | Reject with a reason |
| `GET` | `/{id}/history` | Read stage and review history |

Legacy platform-created partner-onboarding requests remain supported by the original routes. The new required-step gates apply to self-service portal requests, identified by `portal_token_hash`.

## Status sequence and required checks

The existing status enum is reused:

`REQUESTED → BUSINESS_INFORMATION → COMPLIANCE_REVIEW → TECHNICAL_SETUP → API_CREDENTIALS → ACTIVE`

`REJECTED` is terminal.

Portal submissions must have complete legal/contact fields, at least one nominated administrator, and both required documents. Before entering technical setup, required documents must be approved. Before entering API credentials, technical setup must be saved and administrator emails must not already belong to existing FinPilot users. Activation repeats the checks to defend against skipped or stale steps.

Progress is computed from persisted business information, administrator nominations, required document state, technical setup, and activation state.

## Data and security

The Alembic migration adds portal token columns and technical setup JSONB to `partner_onboarding`, plus:

- `partner_onboarding_documents`: document metadata, SHA-256 content digest, review status/notes and storage path.
- `partner_onboarding_administrators`: nominated first admins and hashed invitation tokens.

The existing `partner_onboarding_history` and audit service record request creation, updates, document activity, stage changes, and activation.

Security/operations requirements:

- Serve the portal over HTTPS and apply rate limiting to token-authenticated endpoints.
- Portal tokens and invitation tokens are shown once and hashed at rest. Do not log them.
- Document bytes are stored outside source control. Configure a protected persistent storage root, backups, malware scanning, retention, and least-privilege access before accepting real bank documents.
- Technical setup stores callback/network metadata only; do not collect customer private keys, API secrets, passwords, or certificates as plain JSON fields.
- API keys are high-entropy, returned once, and only the SHA-256 hash is persisted. Store the raw key in the bank's secure secret store immediately.
- Initial API key scopes are deliberately narrow: `customers:read` and `customers:create`. Adjust only through an approved least-privilege policy.
- Tenant and organization creation, admin invitation materialization, API key creation, onboarding activation, and audit entries are performed in a single transaction.
- Activation creates invitations; it does not create user passwords or email invitation links by itself. The bank's invite-token delivery/acceptance frontend must use the existing user invitation acceptance flow.

## Migration and verification

From the backend directory:

```bash
uv run alembic heads
uv run alembic upgrade head
uv run ruff check app/api/partner_onboarding.py app/models/partner_onboarding.py app/repositories/partner_onboarding_repository.py app/schemas/partner_onboarding.py app/services/partner_onboarding_portal_service.py tests/integration/test_partner_onboarding_portal.py
uv run black --check app/api/partner_onboarding.py app/models/partner_onboarding.py app/repositories/partner_onboarding_repository.py app/schemas/partner_onboarding.py app/services/partner_onboarding_portal_service.py tests/integration/test_partner_onboarding_portal.py
uv run pytest tests/integration/test_partner_onboarding.py tests/integration/test_partner_onboarding_portal.py -q
```

The tests require the project's test PostgreSQL database to be available. Apply the migration to a non-production database first and verify the migration graph has one intended head before upgrading production.
