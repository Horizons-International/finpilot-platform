# FinPilot Disaster Recovery Test Record

> Copy this file for every exercise. Store completed evidence in the approved restricted incident/evidence system, not in Git if it contains operationally sensitive details.

## Exercise details

- Exercise ID:
- Date (UTC):
- Exercise lead:
- Scenario: (database loss / corrupted data / deleted files / region outage / ransomware / credential loss / tabletop)
- Production-like or isolated test environment:
- Application release / Git commit:
- PostgreSQL version and pgvector version:
- Participants and roles:

## Recovery point and integrity

- Backup bundle location/identifier (not a public URL):
- Manifest signature verified by:
- SHA-256 verification result:
- Backup creation time (UTC):
- Chosen recovery timestamp (UTC):
- Database restore result:
- Alembic revision restored:
- Storage archive validation result:
- Encryption/decryption/key recovery result:

## Timings and validation

- Incident start (UTC):
- Recovery start (UTC):
- Service restored (UTC):
- **Achieved RTO:**
- Selected recovered data timestamp (UTC):
- **Achieved RPO:**
- `/health` result:
- `/ready` result:
- Authentication/RBAC checks:
- Tenant-isolation checks:
- Customer/verification/compliance/audit evidence checks (IDs only; no PII):
- Document/file bytes and download checks:
- Worker/queue checks:
- Monitoring/logging/TLS checks:

## Results and approval

- Pass/fail:
- Gaps discovered:
- Corrective action / owner / due date:
- Compliance/Data Owner approval:
- Incident Commander approval:
- Next exercise due:

## Evidence attachments

List secure evidence IDs or location references. Do not attach passwords, tokens, private keys, full database dumps, customer data, or decrypted backups to this record.

## Automated backup evidence (complete for scheduled exercises)

- Scheduled task / scheduler job name:
- Schedule/interval:
- Execution identity:
- Output-root and `history.jsonl` entry:
- Bundle configuration archive verified:
- Database dump, document storage, and DB-resident audit records included:
- Environment/config secret files included only under encryption:
- Automated verification exit status:
- Restore-test task status and latest test timestamp:
- Off-site transfer / immutable copy status (if configured):
