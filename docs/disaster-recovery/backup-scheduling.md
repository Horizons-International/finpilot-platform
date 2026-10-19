# Automated Backups, Verification, and History

## Capabilities

`backup.py` creates a unique bundle containing `database.dump`, `globals.sql`, `storage.tar.gz`, and `configuration.tar.gz`, plus a SHA-256 manifest. It runs `verify_bundle` before reporting success. Database-resident audit records are included in the complete PostgreSQL dump; uploaded documents/local files are in `/app/storage`; application/deployment configuration is placed in `configuration.tar.gz`.

Active `.env` files are included in the configuration archive only when `BACKUP_GPG_RECIPIENT` is configured, because the resulting bundle will then be GPG-encrypted. `.env.example` files and approved non-secret configuration files can be included without encryption. Do not infer that a non-encrypted development bundle is safe for production.

The history viewer reads `history.jsonl` from the output root:

```powershell
py -m scripts.disaster_recovery.history --limit 25
py -m scripts.disaster_recovery.history --event backup --json
```

History events include successful/failed backup operations and successful/failed restore-test operations. A verification-only action can be run manually:

```powershell
py -m scripts.disaster_recovery.automation verify-latest --environment development
```

## Windows Task Scheduler

From repository root:

```powershell
.\tools\disaster_recovery\install_scheduled_backup.ps1 -Environment development -IntervalHours 1
```

The script registers an hourly backup task and a daily restore-test task at 03:15. You can set `-IntervalHours` from 1 to 24. Measure actual full backup runtime and data volume before deciding on frequency. If a full database+document backup and transfer cannot complete within the target recovery-point interval, use managed PostgreSQL PITR and file/object-storage replication instead.

Inspect task results:

```powershell
Get-ScheduledTask -TaskName "FinPilot-Automated-Backup", "FinPilot-Daily-Restore-Test" | Get-ScheduledTaskInfo
```

Task history is written to `<output-root>/history.jsonl`. Configure Windows Task Scheduler failure alerts/centralized monitoring separately; this package logs failure status but does not send email, SMS, or paging alerts.

The installer uses the current interactive Windows account. It does not run after that account logs off. Use a dedicated service account or infrastructure scheduler for unattended/production operations.

## Production setup and encryption

Production backup calls require both `BACKUP_GPG_RECIPIENT` (public encryption key identifier) and `BACKUP_GPG_SIGNING_KEY` (signing private-key identifier), a usable GPG installation, and key material in the scheduled account's GPG keyring. Provide those environment variables persistently to the scheduled task account (not just to the interactive shell), then sign out/in to refresh the environment and register:

```powershell
.\tools\disaster_recovery\install_scheduled_backup.ps1 -Environment production -IntervalHours 1
```

Test encryption, signature validation, and decryption after a controlled key-recovery exercise. Keep private decryption keys separate from backup files and host credentials. Use encrypted staging storage: source dump/archive files necessarily exist as plaintext briefly before GPG encryption completes.

## Cloud/off-site backups and retention

The scheduler currently writes verified local bundles; it does not upload to S3, Azure Blob, GCS, or another off-site provider. Configure your approved upload or use managed backup/PITR and versioned/replicated document storage. Off-site copy completion, immutable retention, access separation, capacity alerts, and a tested retention policy are external operational steps. Automatic pruning is deliberately disabled to avoid deleting needed recovery points without an approved policy.

## Restore tests

The daily task selects the latest complete bundle and runs `restore_test.py --require-configuration`; production additionally requires a signed manifest. The test verifies file sizes and hashes, decrypts bundle files when necessary, restores the DB into a throwaway database created from `template0`, validates Alembic metadata, safely extracts document/configuration archives to scratch directories, and drops the throwaway DB on success. On failure the temporary DB is intentionally preserved for inspection.

Example:

```powershell
py -m scripts.disaster_recovery.automation restore-test-latest --environment development
```

This does not replace live DB/storage. It is a technical restore check, not full-service or business-data validation. Complete periodic clean-environment recovery drills and record actual RTO/RPO in `recovery-test-record.md`.

## Linux scheduler alternative

On a trusted backup runner, configure the environment and GPG keyring for the restricted scheduler identity outside the cron file. Example entries (change repository path, interpreter, logs, interval, and restore-test time to fit the deployment):

```cron
0 * * * * cd /srv/finpilot-platform && /usr/bin/python3 -m scripts.disaster_recovery.automation backup --environment production >> /var/log/finpilot-backup.log 2>&1
15 3 * * * cd /srv/finpilot-platform && /usr/bin/python3 -m scripts.disaster_recovery.automation restore-test-latest --environment production >> /var/log/finpilot-restore-test.log 2>&1
```

Cron starts the commands automatically but does not upload backups or page an owner. Secure and rotate the logs, ensure the account can invoke the intended Docker context, and test each command under the scheduler's actual environment before relying on it.
