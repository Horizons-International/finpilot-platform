# Compliance documentation library

## Overview

The compliance-documentation API provides tenant-scoped document metadata, immutable file versions, approval history and structured evidence records. It uses the existing file/storage services and stores content digests with version metadata.

- `backend/app/models/compliance_document.py`: the requested `compliance_documents` model plus version, approval, and evidence models.
- `backend/app/repositories/compliance_document_repository.py`: tenant-filtered document/version/approval/evidence queries.
- `backend/app/services/async_compliance_document_service.py`: validation, uploads through the existing encrypted `FileService` storage layer, hashing, version rules, approval separation of duties, and evidence handling.
- `backend/app/schemas/compliance_document.py`: validated API request/response types.
- `backend/app/api/compliance_documents.py`: REST routes under `/api/v1/compliance-documents`.
- `backend/alembic/versions/cbd20261020_compliance_document_library.py`: database migration.
- `backend/tests/unit/test_compliance_document_models.py`: basic schema/model checks.
- `docs/compliance-documentation/`: evidence catalog, approval workflow, and integration instructions.

## API operations

Base path: `/api/v1/compliance-documents`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/` | Create draft and upload first version (multipart: name, category, file, optional change_summary) |
| GET | `/` | List tenant documents with category/status/limit/offset filters |
| GET | `/{id}` | Read document metadata |
| GET | `/{id}/versions` | List immutable version metadata and SHA-256 digests |
| POST | `/{id}/versions` | Upload another version |
| GET | `/{id}/versions/{version}/download` | Download a version after access checks |
| POST | `/{id}/submit-for-approval` | Submit current version for review |
| POST | `/{id}/approve` | Approve pending version |
| POST | `/{id}/reject` | Reject pending version (review comment required) |
| GET | `/{id}/approvals` | Read approval history |
| POST | `/{id}/evidence` | Attach an evidence reference |
| GET | `/{id}/evidence` | List evidence |
| PATCH | `/{id}/archive` | Archive a document |

Categories include `SECURITY`, `COMPLIANCE`, `OPERATIONS` and `OTHER`. Confirm enum values, MIME limits and response details in the live OpenAPI schema.

## Roles and lifecycle

The API uses role-specific read, write and approver groups. The service enforces document ownership/tenant access and separates the owner from the approver. The lifecycle includes `DRAFT`, `IN_REVIEW`, `APPROVED`, `REJECTED` and `ARCHIVED`; see [approval workflow](APPROVAL_WORKFLOW.md) for the expected process.

These application defaults do not replace the bank's approved records-management, retention, legal-hold and segregation-of-duties policies. Validate the role matrix with Compliance and Security before production.

## Evidence catalogue

Use [EVIDENCE_CATALOG.md](EVIDENCE_CATALOG.md) to identify evidence categories and recommended proof. Use evidence source references as controlled metadata/identifiers only; do not paste tokens, passwords, private keys, secret URLs or personal customer data.

## Setup and verification

From `backend/`:

```bash
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run pytest -q
```

Use a dedicated PostgreSQL test database with pgvector and synthetic documents. Verify list/get/download/version/approve/reject/archive operations for two tenants and multiple roles. Test that cross-tenant IDs do not disclose document metadata or file contents, and that an owner cannot self-approve.

The presence of these files does not certify compliance with a particular regulator or standards framework. Keep independent audit evidence and approvals in the organization's controlled evidence repository.
