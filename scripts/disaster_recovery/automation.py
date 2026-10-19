"""Orchestrate scheduled backup, latest-backup verification, and restore testing."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.disaster_recovery.history import append_history
from scripts.disaster_recovery.manifest import BackupVerificationError, verify_bundle

ROOT = Path(__file__).resolve().parents[2]
_REQUIRED = (
    ("database.dump", "database.dump.gpg"),
    ("storage.tar.gz", "storage.tar.gz.gpg"),
    ("configuration.tar.gz", "configuration.tar.gz.gpg"),
)


def latest_bundle(output_root: Path, *, require_configuration: bool = True) -> Path:
    root = output_root.expanduser().resolve()
    candidates = [
        path
        for path in root.glob("finpilot-dr-*")
        if path.is_dir() and (path / "manifest.json").is_file()
    ]
    valid: list[tuple[str, Path]] = []
    for path in candidates:
        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            names = set(manifest.get("files", {}))
            required = _REQUIRED if require_configuration else _REQUIRED[:2]
            if all(
                any(name in names for name in alternatives) for alternatives in required
            ):
                valid.append((str(manifest.get("created_at_utc", "")), path))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    if not valid:
        scope = (
            "complete database/storage/configuration backup"
            if require_configuration
            else "database/storage backup"
        )
        raise FileNotFoundError(f"No valid {scope} bundle found in {root}")
    return max(valid, key=lambda item: (item[0], item[1].stat().st_mtime))[1]


def _record(root: Path, event: str, status: str, **details: Any) -> None:
    append_history(root, event=event, status=status, **details)


def _run_subprocess(command: list[str]) -> int:
    print("+ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("backup", "verify-latest", "restore-test-latest"),
        help="Operation to run from Task Scheduler or the command line",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / "finpilot-backups",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=ROOT / "docker" / "docker-compose.yml",
    )
    parser.add_argument(
        "--environment",
        default=os.environ.get("ENVIRONMENT", "development"),
        choices=("development", "testing", "production"),
    )
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve()
    compose_file = args.compose_file.resolve()
    if not compose_file.is_file():
        parser.error(f"Compose file not found: {compose_file}")

    if args.mode == "backup":
        command = [
            sys.executable,
            "-m",
            "scripts.disaster_recovery.backup",
            "--output-root",
            str(output_root),
            "--compose-file",
            str(compose_file),
            "--environment",
            args.environment,
        ]
        return _run_subprocess(command)

    started = datetime.now(UTC).isoformat()
    try:
        bundle = latest_bundle(output_root)
        if args.mode == "verify-latest":
            manifest = verify_bundle(
                bundle, require_signature=args.environment == "production"
            )
            names = set(manifest["files"])
            for alternatives in _REQUIRED:
                if not any(name in names for name in alternatives):
                    raise BackupVerificationError(
                        "Latest backup is missing required scope file: "
                        f"{alternatives[0]}"
                    )
            print(f"Latest backup verification passed: {bundle} ({len(names)} files).")
            _record(
                output_root,
                "verify",
                "success",
                bundle_dir=bundle,
                details=f"Verified {len(names)} files; started_at_utc={started}",
            )
            return 0

        command = [
            sys.executable,
            "-m",
            "scripts.disaster_recovery.restore_test",
            str(bundle),
            "--compose-file",
            str(compose_file),
            "--require-configuration",
        ]
        if args.environment == "production":
            command.append("--require-signature")
        return _run_subprocess(command)
    except (BackupVerificationError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"AUTOMATION FAILED: {exc}", file=sys.stderr)
        try:
            event = "verify" if args.mode == "verify-latest" else "restore-test"
            _record(
                output_root,
                event,
                "failure",
                details=str(exc),
                started_at_utc=started,
            )
        except (OSError, ValueError):
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
