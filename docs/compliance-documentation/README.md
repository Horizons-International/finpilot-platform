# FinPilot Compliance Documentation Module

This package adds a tenant-scoped compliance library to FinPilot with immutable file versions, approval history, controlled downloads, and explicit evidence records.

## Included

- `backend/app/models/compliance_document.py`: the requested `compliance_documents` model plus version, approval, and evidence models.
- `backend/app/repositories/compliance_document_repository.py`: tenant-filtered document/version/approval/evidence queries.
- `backend/app/services/compliance_document_service.py`: validation, uploads through the existing encrypted `FileService` storage layer, hashing, version rules, approval separation of duties, and evidence handling.
- `backend/app/schemas/compliance_document.py`: validated API request/response types.
- `backend/app/api/compliance_documents.py`: REST routes under `/api/v1/compliance-documents`.
- `backend/alembic/versions/cbd20261020_compliance_document_library.py`: database migration.
- `backend/tests/unit/test_compliance_document_models.py`: basic schema/model checks.
- `docs/compliance-documentation/`: evidence catalog, approval workflow, and integration instructions.

## API operations

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/v1/compliance-documents` | Create a draft and upload its first file version (multipart: `name`, `category`, `file`, optional `change_summary`) |
| `GET` | `/api/v1/compliance-documents` | List tenant documents; optional `category`, `status`, `limit`, `offset` |
| `GET` | `/api/v1/compliance-documents/{id}` | Retrieve document metadata |
| `GET` | `/api/v1/compliance-documents/{id}/versions` | List immutable version metadata and SHA-256 digests |
| `POST` | `/api/v1/compliance-documents/{id}/versions` | Upload a new file version |
| `GET` | `/api/v1/compliance-documents/{id}/versions/{version}/download` | Download a version after tenant and role checks |
| `POST` | `/api/v1/compliance-documents/{id}/submit-for-approval` | Submit current version for review |
| `POST` | `/api/v1/compliance-documents/{id}/approve` | Approve a pending submission |
| `POST` | `/api/v1/compliance-documents/{id}/reject` | Reject a pending submission (review comment required) |
| `GET` | `/api/v1/compliance-documents/{id}/approvals` | Read approval audit history |
| `POST` | `/api/v1/compliance-documents/{id}/evidence` | Attach a structured evidence record/reference |
| `GET` | `/api/v1/compliance-documents/{id}/evidence` | List evidence records |
| `PATCH` | `/api/v1/compliance-documents/{id}/archive` | Archive a document |

Categories are `SECURITY`, `COMPLIANCE`, `OPERATIONS`, and `OTHER`. File uploads use the existing configured maximum file size and are restricted to supported documentation/media types. Evidence source references are metadata only: do not paste credentials, tokens, secret URLs, or customer personal data into them.

## Roles and access model

- Any authenticated FinPilot role can read documents in its own tenant; repository/service queries enforce the authenticated tenant.
- `Administrator`, `Organization Admin`, `Compliance Manager`, and `Compliance Officer` can create documents, versions, and evidence.
- `Administrator`, `Organization Admin`, and `Compliance Manager` can approve/reject submissions and archive documents.
- A document owner cannot approve their own document.
- A document in `IN_REVIEW` cannot be versioned or archived. A rejected document can be revised and resubmitted.

These are application-level defaults, not a substitute for a bank's approved records-retention, segregation-of-duties, and document-classification policy. Tailor the role matrix to the deployment's governance requirements.

## Setup

1. Copy the files into the repository root, preserving paths.
2. Follow `IMPLEMENTATION_NOTES.md` to register the router and model with the current application and Alembic metadata.
3. From `backend/`, verify the migration base against the local history, run `uv run alembic upgrade head`, then run tests.
4. Test with two tenants and at least two roles. Verify that another tenant cannot list, retrieve, download, version, approve, archive, or attach evidence to a document it does not own.
5. Upload a synthetic PDF/text file, check the stored SHA-256 and `file_id`, perform submit → approve/reject, and confirm version and approval records persist.

The ZIP is code preparation, not a claim that a migration or integration test has already passed against your running PostgreSQL instance.
