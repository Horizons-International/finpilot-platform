"""Verify a backup and test a database restore without overwriting live data."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from scripts.disaster_recovery.manifest import BackupVerificationError, verify_bundle

ROOT = Path(__file__).resolve().parents[2]


def compose(compose_file: Path, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), *args]


def run(command: list[str], *, stdin_stream: BinaryIO | None = None) -> str:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=ROOT,
        stdin=stdin_stream,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {error}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def resolve_backup_files(
    bundle: Path, manifest: dict, scratch: Path
) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for stored_name in manifest["files"]:
        source = bundle / stored_name
        if stored_name.endswith(".gpg"):
            if shutil.which("gpg") is None:
                raise RuntimeError(
                    f"Backup file {stored_name} is encrypted but gpg is unavailable"
                )
            output = scratch / stored_name[:-4]
            with output.open("wb") as target:
                result = subprocess.run(
                    ["gpg", "--batch", "--decrypt", str(source)],
                    stdout=target,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            if result.returncode != 0:
                raise RuntimeError(
                    "Could not decrypt backup file; check the authorized private key. "
                    + result.stderr.decode("utf-8", errors="replace").strip()
                )
            resolved[output.name] = output
        else:
            resolved[stored_name] = source
    return resolved


def validate_storage_archive(archive_path: Path) -> tuple[int, int]:
    """Validate the archive and extract it to temporary scratch, never live storage."""
    count = 0
    regular_file_bytes = 0
    with tempfile.TemporaryDirectory(prefix="finpilot-dr-storage-test-") as temporary:
        target = Path(temporary).resolve()
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise RuntimeError(
                        f"Unsafe path in storage archive: {member.name!r}"
                    )
                # A storage backup does not need links. Reject links so an archive
                # cannot write outside the scratch restore directory.
                if member.issym() or member.islnk() or member.isdev():
                    raise RuntimeError(
                        f"Unsupported link/device in storage archive: {member.name!r}"
                    )
                count += 1
                if member.isfile():
                    regular_file_bytes += member.size
            archive.extractall(target, members=members, filter="data")
    return count, regular_file_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle_dir", type=Path, help="Path to one finpilot-dr-* backup bundle"
    )
    parser.add_argument(
        "--compose-file", type=Path, default=ROOT / "docker" / "docker-compose.yml"
    )
    parser.add_argument(
        "--keep-database",
        action="store_true",
        help="Keep the throwaway restored DB after a successful test",
    )
    parser.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail unless manifest.json.asc is present and valid",
    )
    args = parser.parse_args()

    bundle = args.bundle_dir.expanduser().resolve()
    compose_file = args.compose_file.resolve()
    if not bundle.is_dir():
        parser.error(f"Backup bundle directory not found: {bundle}")
    if not compose_file.is_file():
        parser.error(f"Compose file not found: {compose_file}")

    environment = os.environ.get("ENVIRONMENT", "development").casefold()
    require_signature = args.require_signature or environment == "production"
    restore_db = "finpilot_dr_restore_test_" + datetime.now(UTC).strftime(
        "%Y%m%d%H%M%S"
    )
    database_created = False

    try:
        manifest = verify_bundle(bundle, require_signature=require_signature)
        print(f"Manifest/hash verification passed ({len(manifest['files'])} files).")

        with tempfile.TemporaryDirectory(prefix="finpilot-dr-test-") as scratch_str:
            files = resolve_backup_files(bundle, manifest, Path(scratch_str))
            dump_path = files.get("database.dump")
            storage_path = files.get("storage.tar.gz")
            if dump_path is None:
                raise BackupVerificationError(
                    "Bundle does not contain database.dump or database.dump.gpg"
                )
            if storage_path is None:
                raise BackupVerificationError(
                    "Bundle does not contain storage.tar.gz or storage.tar.gz.gpg"
                )

            # template0 intentionally has no collation-dependent objects, so it
            # can be used even when template1's recorded collation version is stale.
            # This enables the throwaway restore test; it does not repair a mismatch
            # in the source database or the PostgreSQL cluster.
            run(
                compose(
                    compose_file,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-lc",
                    'createdb -U "$POSTGRES_USER" --template=template0 "$1"',
                    "sh",
                    restore_db,
                )
            )
            database_created = True
            with dump_path.open("rb") as dump_stream:
                run(
                    compose(
                        compose_file,
                        "exec",
                        "-T",
                        "postgres",
                        "sh",
                        "-lc",
                        "pg_restore --exit-on-error --no-owner --no-privileges "
                        '-U "$POSTGRES_USER" -d "$1"',
                        "sh",
                        restore_db,
                    ),
                    stdin_stream=dump_stream,
                )

            table_count = run(
                compose(
                    compose_file,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-lc",
                    'psql -X -A -t -U "$POSTGRES_USER" -d "$1" -c '
                    '"SELECT count(*) FROM information_schema.tables '
                    "WHERE table_schema='public' AND table_type='BASE TABLE'\"",
                    "sh",
                    restore_db,
                )
            )
            try:
                tables = int(table_count)
            except ValueError as exc:
                raise RuntimeError(
                    f"Unexpected table count query output: {table_count!r}"
                ) from exc
            if tables < 1:
                raise RuntimeError("Restored database has no public base tables")

            alembic = run(
                compose(
                    compose_file,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-lc",
                    'psql -X -A -t -U "$POSTGRES_USER" -d "$1" -c '
                    "\"SELECT to_regclass('public.alembic_version') IS NOT NULL\"",
                    "sh",
                    restore_db,
                )
            )
            if alembic.strip().lower() not in {"t", "true"}:
                raise RuntimeError(
                    "Restored database is missing public.alembic_version"
                )
            revision = run(
                compose(
                    compose_file,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-lc",
                    'psql -X -A -t -U "$POSTGRES_USER" -d "$1" -c '
                    '"SELECT version_num FROM alembic_version LIMIT 1"',
                    "sh",
                    restore_db,
                )
            )
            if not revision:
                raise RuntimeError("The restored Alembic version table has no revision")

            member_count, storage_bytes = validate_storage_archive(storage_path)
            print(
                f"Database restore passed: {tables} public tables; "
                f"Alembic revision {revision}."
            )
            print(
                f"Storage archive passed: {member_count} archive entries; "
                f"{storage_bytes} uncompressed file bytes."
            )
            print(
                "NOTE: this is a technical restore test, not business-data, "
                "tenant-isolation, or full-service validation."
            )

        if database_created and not args.keep_database:
            run(
                compose(
                    compose_file,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-lc",
                    'dropdb -U "$POSTGRES_USER" --if-exists "$1"',
                    "sh",
                    restore_db,
                )
            )
            database_created = False
            print("Throwaway restore-test database dropped.")
        elif database_created:
            print(f"Throwaway restore-test database preserved: {restore_db}")
        return 0
    except (
        BackupVerificationError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"RESTORE TEST FAILED: {exc}", file=sys.stderr)
        if database_created:
            print(
                f"Throwaway restore-test database left for inspection: {restore_db}",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
