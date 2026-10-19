"""Create a FinPilot PostgreSQL + local file-storage backup bundle."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.disaster_recovery.manifest import write_manifest

ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=True, text=True)


def compose(compose_file: Path, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), *args]


def repository_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def encrypt_bundle_files(bundle_dir: Path, recipient: str) -> None:
    if shutil.which("gpg") is None:
        raise RuntimeError("BACKUP_GPG_RECIPIENT is set, but gpg is not installed")
    files = [p for p in bundle_dir.iterdir() if p.is_file()]
    for path in files:
        encrypted = path.with_name(path.name + ".gpg")
        run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--trust-model",
                "always",
                "--recipient",
                recipient,
                "--output",
                str(encrypted),
                "--encrypt",
                str(path),
            ]
        )
        path.unlink()


def sign_manifest(manifest_path: Path, signing_key: str) -> None:
    run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--local-user",
            signing_key,
            "--armor",
            "--detach-sign",
            "--output",
            str(manifest_path.with_name("manifest.json.asc")),
            str(manifest_path),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / "finpilot-backups",
        help="Backup output root (default: ~/finpilot-backups; keep it outside Git)",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=ROOT / "docker" / "docker-compose.yml",
        help="Docker Compose file path",
    )
    parser.add_argument(
        "--environment",
        default=os.environ.get("ENVIRONMENT", "development"),
        choices=("development", "testing", "production"),
    )
    args = parser.parse_args()

    compose_file = args.compose_file.resolve()
    if not compose_file.is_file():
        parser.error(f"Compose file not found: {compose_file}")

    recipient = os.environ.get("BACKUP_GPG_RECIPIENT", "").strip()
    signing_key = os.environ.get("BACKUP_GPG_SIGNING_KEY", "").strip()
    if args.environment == "production" and (not recipient or not signing_key):
        print(
            "ERROR: production backups require BACKUP_GPG_RECIPIENT and "
            "BACKUP_GPG_SIGNING_KEY.",
            file=sys.stderr,
        )
        return 2
    if bool(recipient) != bool(signing_key) and args.environment == "production":
        print(
            "ERROR: production encryption and signing must both be configured.",
            file=sys.stderr,
        )
        return 2

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = args.output_root.expanduser().resolve() / f"finpilot-dr-{stamp}"
    bundle_dir.mkdir(parents=True, exist_ok=False)
    # Restrict access to backup files where POSIX filesystem permissions apply.
    try:
        bundle_dir.chmod(0o700)
    except OSError:
        pass

    remote_id = stamp.replace("T", "_").replace("Z", "")
    remote_db = f"/tmp/finpilot_dr_{remote_id}.dump"
    remote_globals = f"/tmp/finpilot_dr_{remote_id}_globals.sql"
    remote_storage = f"/tmp/finpilot_dr_{remote_id}_storage.tar.gz"
    jobs = [
        (
            "postgres",
            remote_db,
            (
                'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                f'--format=custom --no-owner --no-privileges > "{remote_db}"'
            ),
            "database.dump",
        ),
        (
            "postgres",
            remote_globals,
            f'pg_dumpall --globals-only -U "$POSTGRES_USER" > "{remote_globals}"',
            "globals.sql",
        ),
        (
            "backend",
            remote_storage,
            f'tar -czf "{remote_storage}" -C /app/storage .',
            "storage.tar.gz",
        ),
    ]

    try:
        # Docker exec writes bytes inside the container; docker compose cp avoids
        # PowerShell's text-oriented redirection corrupting a binary pg_dump.
        for service, remote_path, remote_command, output_name in jobs:
            run(
                compose(
                    compose_file, "exec", "-T", service, "sh", "-lc", remote_command
                )
            )
            try:
                run(
                    compose(
                        compose_file,
                        "cp",
                        f"{service}:{remote_path}",
                        str(bundle_dir / output_name),
                    )
                )
            finally:
                subprocess.run(
                    compose(
                        compose_file, "exec", "-T", service, "rm", "-f", remote_path
                    ),
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

        if recipient:
            encrypt_bundle_files(bundle_dir, recipient)

        manifest_path = write_manifest(
            bundle_dir,
            environment=args.environment,
            repository_commit=repository_commit(),
        )
        if signing_key:
            sign_manifest(manifest_path, signing_key)

        print(f"Backup bundle created: {bundle_dir}")
        print(f"Manifest: {manifest_path}")
        print(
            "Next: copy this bundle to encrypted, off-site, access-controlled storage."
        )
        if not recipient:
            print(
                "WARNING: this bundle is not GPG-encrypted; "
                "suitable only for controlled non-production use."
            )
        return 0
    except (subprocess.CalledProcessError, RuntimeError, OSError) as exc:
        print(f"ERROR: backup failed: {exc}", file=sys.stderr)
        if args.environment == "production":
            # Avoid leaving plaintext production exports in a partial bundle if
            # encryption/signing failed. This is logical deletion, not guaranteed
            # physical erasure; use encrypted staging storage too.
            for partial in bundle_dir.iterdir():
                if partial.is_file() and not partial.name.endswith(".gpg"):
                    try:
                        partial.unlink()
                    except OSError:
                        print(
                            f"WARNING: could not remove plaintext partial {partial}",
                            file=sys.stderr,
                        )
            print(
                "Removed remaining plaintext partial files where possible.",
                file=sys.stderr,
            )
        print(f"Partial bundle retained for inspection: {bundle_dir}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
