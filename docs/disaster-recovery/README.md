# Disaster Recovery Plan — FinPilot

**Document owner:** Platform Owner  
**Approvers:** Platform Owner, DBA/Database Operations, Security, Compliance  
**Review cadence:** Quarterly and after material infrastructure/application changes  
**Classification:** Internal — operationally sensitive

## 1. Purpose and scope

This plan describes how FinPilot is backed up, restored, validated, and returned to service after a destructive deployment, database/storage failure, infrastructure outage, security incident, or regional failure. It covers the FastAPI backend, PostgreSQL with pgvector, the mounted local file-storage volume, runtime configuration/secrets, Alembic schema state, and the background workers in `docker/docker-compose.yml`.

It does not replace bank-specific business-continuity obligations, cloud-provider runbooks, incident-response policy, legal retention requirements, or a tested high-availability architecture.

## 2. Recovery targets

Proposed initial service-level objectives:

| Target | Proposed objective | Conditions before the objective can be claimed |
|---|---|---|
| RTO — critical API and database | 4 hours | Known-good infrastructure/provisioning, documented access to secrets, tested database restore, application images/configuration available, named responders on call, and drill proves elapsed recovery time under 4 hours. |
| RPO — customer/compliance database | 1 hour | Scheduled recoverable backup at least hourly, or tested PostgreSQL WAL/PITR with recovery points no more than one hour apart, with off-site copies and alerting. |
| RPO — uploaded documents and generated files | 1 hour | Storage replication/versioning or archive copies no more than one hour apart and coordinated with database restore points. |
| Worker restoration | 4 hours after DB/API | Database restored first; idempotent/retry behavior reviewed; workers enabled only after API and database validation. |

**These are proposed targets, not current guarantees.** The Compose file defines named Docker volumes, but does not configure off-site backups, automatic backup scheduling, WAL archiving/PITR, or storage replication. Until those controls are deployed and recovery-tested, actual RPO/RTO are not established. If a business owner chooses different limits, record them in the drill evidence and update this table.

## 3. Backup strategy

### 3.1 What must be backed up

1. **PostgreSQL database:** `pg_dump` custom-format backup including schema, data, and migration state. Preserve extensions/schema requirements such as pgvector on the target.
2. **Cluster globals:** a `pg_dumpall --globals-only` export for role/privilege recovery. Review before applying to a replacement cluster; don't blindly overwrite an existing identity/role configuration.
3. **File storage:** archive of `/app/storage` from the running backend container, which shares the `finpilot_storage` Compose volume. It must be restored consistently with file metadata in PostgreSQL.
4. **Configuration and secrets:** store deployment config, environment definitions without embedding plaintext credentials, key identifiers, secret-manager references, allowed network rules, and TLS certificates/renewal instructions in an access-controlled system. Never save production `.env` files or secrets in this backup bundle or Git.
5. **Application artifact:** record Git commit/release and image tag/digest. Keep the corresponding deployable artifact available independently of the production host.

### 3.2 Frequency and retention (initial recommendation)

- PostgreSQL: use managed automated backups with PITR/WAL archiving where available. As a minimum fallback, run the included full backup at least hourly if the one-hour RPO is required and the volume/time/cost is acceptable.
- File storage: use versioned/replicated object storage or schedule the included storage archive at a frequency that meets the same RPO. Full archives can become expensive for large storage volumes.
- Keep a separate off-site copy with access controls and immutable/retention-locked versions where supported.
- Initial retention policy to review with Compliance: daily recovery points for 35 days, weekly recovery points for 12 weeks, and monthly recovery points for 12 months. Replace these defaults with bank-specific regulatory, legal-hold, and contract requirements before production use.
- Run a restore test monthly and after major database, storage, encryption, or infrastructure changes. Perform a documented tabletop exercise at least quarterly.

### 3.3 Encryption and integrity

- Production backups must be encrypted with GPG to a managed recipient key and have the manifest digitally signed by a managed signing key. Keep private decryption/signing keys separate from the backup storage account and target host.
- Store backups on encrypted disks while creating, encrypting, staging, and restoring them. Deleting a plaintext staging file does not guarantee secure physical erasure on SSDs or copy-on-write filesystems.
- Verify the manifest signature and every SHA-256 digest before any restore.
- Use a separate credential/role with read/write rights to the backup target; production runtime credentials should not have permission to delete/expire all backups.
- Periodically prove decryption works with a controlled key-recovery process.

## 4. Recovery responsibilities

| Role | Responsibilities |
|---|---|
| Incident Commander / Platform Owner | Declare recovery incident, determine severity, assign a recovery lead, approve service restoration and external status communications, track RTO. |
| Database Administrator / Database Operations | Protect the failed instance from writes, provision/validate replacement PostgreSQL, select recovery point, restore database and required roles/extensions, verify data integrity, record recovered timestamp/RPO. |
| Application/Platform Engineer | Provision clean host/container environment, retrieve approved release and configuration, restore file storage, apply only the necessary migrations, bring API up, run smoke tests, restore workers in a controlled order. |
| Security/Infrastructure | Validate host/network identity, TLS, secret availability and rotation needs, log access, backup signatures/encryption, and whether the incident may be a compromise rather than an availability failure. |
| Compliance/Data Owner | Determine legal holds/retention constraints, validate a representative set of compliance records and documents, approve data consistency, and decide whether notifications or regulatory escalation are required. |
| Communications/Support | Send approved internal/customer status updates, keep timestamps and incident decisions, and track service-impact reports. One person may fill multiple roles in a small team, but assignments must be explicit for each incident. |

Maintain actual names, primary/backup contacts, paging details, secret-manager access process, cloud account IDs, and vendor escalation information in a restricted contact sheet that is accessible if the primary developer laptop or repository is unavailable. Do not put credentials in this runbook.

## 5. Incident classification and first actions

1. Record discovery time, affected service, reporter, symptoms, and current recovery target.
2. Incident Commander declares an incident and selects a recovery lead.
3. **For suspected compromise/ransomware:** isolate affected hosts/accounts, preserve logs and evidence, consult Security before restoring, and don't reconnect a potentially compromised host. Restore into clean infrastructure using known-good credentials.
4. Stop destructive automation and restrict write traffic if continuing writes could corrupt the restore point. Communicate maintenance status.
5. Confirm backup repository availability from a clean identity/session; validate signatures, encryption-key availability, integrity hashes, and timestamps. Select a point-in-time that predates corruption/compromise.
6. Preserve the failed resources and logs unless Security explicitly authorizes disposal.

## 6. System restoration procedure

### Phase A — prepare clean infrastructure

1. Use a clean host/cluster and a known-good, approved FinPilot release. Don't restore onto an untrusted or still-failing system.
2. Configure Docker/Compose or the production runtime. Recreate PostgreSQL at the supported major version, pgvector extension availability, network rules, health monitoring, disk encryption, and TLS.
3. Recover secrets from the secret manager. Rotate database, API, JWT, encryption, webhook, and provider credentials if exposure is plausible. Encryption keys that protect database fields or external files must remain available; rotation needs an explicit re-encryption plan.
4. Keep public traffic and write-capable workers disabled until data recovery validation is complete.

### Phase B — select and verify a recovery point

1. Locate the incident's most recent known-good, off-site backup set.
2. Run the package's `restore_test.py` against that bundle when there is a functioning isolated PostgreSQL target available. This creates a throwaway database and does not replace production data.
   The test creates its throwaway database from `template0`, which avoids failure solely because `template1` has a stale collation-version record. If PostgreSQL reports a collation-version mismatch in the source databases, treat it as a separate database-maintenance issue: use a matching PostgreSQL/container OS collation library or rebuild affected indexes before refreshing the recorded version. A successful restore test does not clear that warning.
3. Verify the bundle's `manifest.json` signature (if signed), SHA-256 hashes, expected files, dump readability, storage archive readability, timestamp, and release/commit metadata.
4. Select the intended recovery time; record the difference between incident time and recoverable data time. That difference is the achieved RPO.

### Phase C — restore database and file storage

1. Stop API writers and background workers. Confirm no job will enqueue/execute actions against a half-restored system.
2. Provision an empty replacement database with the required PostgreSQL major version and required extensions such as `vector`.
3. Inspect the globals export; create/restore required database roles deliberately. Avoid replaying role definitions without review when the target cluster already has security/managed-service roles.
4. Decrypt and copy the database dump to the trusted restore host. Verify its digest again. Restore the dump into a **new/empty target database** using `pg_restore --exit-on-error --no-owner --no-privileges -d <target_db> <database.dump>`. Do not use a casual `--clean` restore against the live database.
5. Restore the matching storage archive to the proper storage volume/path, or reattach/restore the corresponding versioned object-storage snapshot. Preserve ownership, access modes, and encrypted-file requirements. Do not mix a database backup from one timestamp with a document volume from an incompatible timestamp without assessing consistency.
6. Compare the restored schema's `alembic_version` to the release expected by that application version. Run `alembic upgrade head` only if required by the release plan and after reviewing pending migrations; never use migrations as a substitute for restoring missing data.

For the local Compose setup, the provided scripts back up the PostgreSQL service `postgres` and the file volume mounted at `/app/storage` in the `backend` service. They intentionally do not include pgAdmin state, container writable layers, or a remote secret manager.

### Phase D — validate and restore service

1. Run DB checks: database accepts connections; expected public tables exist; Alembic revision is present; no unexpected recovery errors.
2. Run the FastAPI health and readiness probes, `/health` and `/ready`, plus authentication/login smoke checks.
3. Validate at least one customer, verification case, compliance case, audit history record, and uploaded document using approved test IDs. Confirm records and corresponding file bytes correspond to the selected point-in-time. Avoid exposing sensitive payloads in logs or drill notes.
4. Verify tenant isolation using two test tenants, RBAC restrictions, audit logging, TLS, and file downloads.
5. Start API service first; then enable only workers needed for safe operation (for example, report-export and webhook delivery after reviewing their pending queues). Monitor errors and repeated/duplicate jobs.
6. Compliance/Data Owner and Incident Commander approve restoration. Record restored timestamp, achieved RPO and RTO, validation, unresolved gaps, and next actions.
7. Gradually reopen traffic, monitor latency/error rates and queue backlogs, and make an approved status update.

## 7. Recovery drill and evidence

- Run the monthly technical restore test against a recent backup in an isolated database. The `restore_test.py` command is a safe first step.
- At least quarterly, execute a tabletop exercise with primary and backup responders. Include a scenario where both the application host and one credential are unavailable.
- Periodically perform a full recovery on clean infrastructure to verify secrets, networking, TLS, database roles/extensions, storage, workers, and production-like validation. A dump restore alone is not a complete disaster-recovery test.
- Use `recovery-test-record.md` to record the run. Attach command output, start/end UTC timestamps, manifest hash/signature result, selected backup timestamp, recovered timestamp, achieved RTO/RPO, restored table/record checks (without personal data), approvals, defects and owners.
- A test is failed if data is inconsistent, decryption/keys are unavailable, tenant/RBAC checks fail, the storage archive cannot be restored, or the agreed time/data-loss objective is exceeded.

## 8. Contact sheet, dependencies and operational readiness

Keep a private, current contact sheet with: incident commander primary/backup, DBA primary/backup, security escalation, compliance owner, cloud/hosting provider escalation, DNS/registrar, TLS certificate owner, secret-manager administrator, backup repository administrator, and business communications approver.

Before declaring DR ready, verify:

- [ ] A backup schedule exists and failures page an owner.
- [ ] Database and file backups exist off-site in a separate failure domain.
- [ ] Backup account cannot be deleted by normal application credentials.
- [ ] Production backup bundles are encrypted and signed.
- [ ] Private keys and secret-recovery instructions are available to an authorized backup responder.
- [ ] PostgreSQL/pgvector version and required extensions are documented.
- [ ] Application release artifact and config can be recovered without the production host.
- [ ] Named people can follow these steps without the original implementer.
- [ ] A successful recovery drill demonstrates the stated RTO and RPO.

## 9. Automated backup execution and history

The extended backup tools now produce a verified bundle containing the PostgreSQL custom-format dump (including all database-resident audit records), PostgreSQL globals export, `/app/storage` document/file archive, and `configuration.tar.gz`. Active `.env` files are only included in the configuration archive when GPG encryption is configured; non-secret deployment configuration and example files are included where available. Backup output is indexed in `<output-root>/history.jsonl`.

From the repository root:

```powershell
py -m scripts.disaster_recovery.backup --environment development
py -m scripts.disaster_recovery.history --limit 25
py -m scripts.disaster_recovery.automation verify-latest --environment development
py -m scripts.disaster_recovery.automation restore-test-latest --environment development
```

To register local Windows tasks (hourly backup and daily restore test):

```powershell
.\tools\disaster_recovery\install_scheduled_backup.ps1 -Environment development -IntervalHours 1
```

For production, configure GPG recipient and signing key identifiers for the scheduler identity before installing the tasks with `-Environment production`. Production-mode backups fail closed without encryption/signing configuration. The Task Scheduler installer uses the current interactive Windows account and runs only while that account is logged on; production should use a restricted unattended service account or an approved infrastructure scheduler.

The scheduler writes local verified backups and history only. Off-site copy, managed PITR/replication, alert delivery, backup retention/pruning, and complete service-level recovery testing remain operational controls to configure and validate separately. Do not state production DR readiness until those controls are proven in the target deployment.
