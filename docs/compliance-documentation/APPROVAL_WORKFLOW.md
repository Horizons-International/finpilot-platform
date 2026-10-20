# Document lifecycle and approval workflow

## Statuses

- **DRAFT** — a writable working document version.
- **IN_REVIEW** — the current version has a pending approval request; it cannot be replaced while review is pending.
- **APPROVED** — the exact version recorded in the approval record has been approved.
- **REJECTED** — reviewer returned the version; add a new immutable version before resubmitting.
- **ARCHIVED** — retained for evidence/history and no longer editable through the versioning API.

## Standard flow

1. A compliance manager/officer or authorized administrator creates a document and uploads its initial file as version 1.
2. The API stores file metadata through FinPilot's existing `FileService` and storage implementation, and stores a SHA-256 digest for verification.
3. The owner adds related evidence records and submits the current version for approval.
4. A permitted approver different from the document owner approves or rejects it with a review comment; the approval row records reviewer, decision, time, comments, and version.
5. Rejected work is revised as a new version and submitted again. Prior versions and approval rows remain available for audit.
6. A manager/admin can archive a document only when no approval is pending.

## Evidence and version integrity

- A version row is append-only from the API: changing file contents creates another row instead of overwriting the previous file.
- Keep `content_sha256`, the version number, uploader and upload timestamp alongside each version.
- For a regulatory pack, export/capture the document metadata, all relevant versions, approval history, evidence records, and referenced evidence in a controlled manner.
- Configure storage backup, retention, access logging, and deletion policies in line with the bank's records schedule. This module does not independently enforce legal holds or retention expiry.

## Review controls

Before production use, agree the role matrix and required approval quorum with compliance/security stakeholders. The delivered workflow implements one approval decision per submission and prevents owner self-approval; maker-checker requirements beyond that (two-person approval, external signing, expiry reminders, legal holds) should be added when required by policy.
