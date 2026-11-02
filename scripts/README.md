# Repository scripts

Operational Python scripts live under `scripts/`; they are not the active API application package. The main script collection in this repository is `scripts/disaster_recovery/`.

## Disaster-recovery commands

Run commands from the repository root. The scripts use the configured Docker Compose services and environment settings; use a disposable test environment before testing restores.

Create a development backup:

```powershell
py -m scripts.disaster_recovery.backup --environment development
```

Verify and test-restore a bundle without overwriting the source database (see the command-line help for required arguments and options):

```powershell
py -m scripts.disaster_recovery.restore_test --help
```

Other modules provide automation, backup history, manifest verification and tool tests.

A backup contains more than a database dump: verify that the configured file-storage data and any required configuration material are captured. Production backup encryption/signing requirements are enforced by the backup command; configure key material through secure environment variables, not source files.

Detailed procedure: [Disaster recovery guide](../docs/disaster-recovery/README.md).
