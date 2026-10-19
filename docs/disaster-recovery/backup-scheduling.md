# Backup Scheduling and Monitoring

The backup tool is on-demand; the repository does not currently configure an automated backup scheduler or off-site storage. Schedule it only after choosing a protected destination and confirming expected database/storage size and runtime.

## Preferred production approach

Use a managed PostgreSQL backup/PITR service and versioned/replicated object storage in a separate failure domain. Alert on missing recovery points, broken replication, exhausted capacity, failed restore drills, and inaccessible encryption keys. This is generally safer and more scalable than repeatedly creating full copies of a large storage volume.

## Full-bundle fallback

If using the bundled full-dump script to target RPO ≤ 1 hour, schedule it at least hourly only if a full database plus full local-storage archive can reliably complete within that window and the off-site transfer also completes before the deadline. If not, the target is not met; choose PITR and storage replication instead.

Every successful run creates a distinct bundle directory. The job must upload/copy the complete directory, including `manifest.json` and any `manifest.json.asc`, into encrypted off-site storage. Do not regard a bundle on the same host as a disaster-recovery copy.

### Linux host example (adapt and test before enabling)

Install the scheduler on a trusted backup runner; ensure Docker access and GPG public/signing keys are provisioned for that service account. Environment variables used for production encryption must be supplied by a secret manager or restricted service environment, not written inline into the cron file.

```cron
# Example only: run a full bundle every hour. Confirm duration/capacity first.
0 * * * * cd /srv/finpilot-platform && /usr/bin/python3 -m scripts.disaster_recovery.backup --environment production >> /var/log/finpilot-dr-backup.log 2>&1
```

This example creates local bundles but does not implement the off-site copy. Add an approved uploader or provider backup mechanism and alerting; do not mark the control complete until end-to-end off-site recovery is tested. Protect and rotate the log, since it reveals operational details.

### Windows Task Scheduler example

- **Program/script:** path to the approved Python interpreter, for example `C:\Python312\python.exe`.
- **Add arguments:** `-m scripts.disaster_recovery.backup --environment production --output-root D:\FinPilotBackups`
- **Start in:** the cloned FinPilot repository root.
- **Trigger:** hourly only if the measured full backup and upload finish within the target RPO; otherwise use managed PITR/replication.
- **Run as:** restricted backup service account with the minimum Docker/backup permissions needed.
- **Environment and GPG:** configure `BACKUP_GPG_RECIPIENT` and `BACKUP_GPG_SIGNING_KEY` in the restricted service account's environment/keyring or secret-management integration. Avoid storing key material in the task arguments.
- **Failure action:** alert an owner on nonzero exit or missed run. Ensure the scheduled process copies the complete bundle to an approved off-site location.

## Monitoring signals

At minimum monitor:

- Latest successful database recovery point age.
- Latest successful storage backup/replication age.
- End-to-end time from backup start through off-site-copy completion.
- Backup and restore-test exit code.
- GPG signing/encryption/key availability result.
- Off-site object count, size growth, immutable retention status, and capacity.
- Most recent successful isolated restore drill and its achieved RTO/RPO.
