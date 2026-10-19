"""Verify a backup and test a database restore without overwriting live data."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from scripts.disaster_recovery.history import append_history
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
                error = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    "Could not decrypt backup file; check the authorized private key. "
                    + error
                )
            resolved[output.name] = output
        else:
            resolved[stored_name] = source
    return resolved


def validate_archive(
    archive_path: Path, *, purpose: str = "archive"
) -> tuple[int, int]:
    """Validate and safely extract a tar.gz to scratch; reject traversal and links."""
    count = 0
    regular_file_bytes = 0
    with tempfile.TemporaryDirectory(
        prefix=f"finpilot-dr-{purpose}-test-"
    ) as temporary:
        target = Path(temporary).resolve()
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise RuntimeError(
                        f"Unsafe path in {purpose} archive: {member.name!r}"
                    )
                if (
                    member.issym()
                    or member.islnk()
                    or member.isdev()
                    or member.isfifo()
                ):
                    raise RuntimeError(
                        f"Unsupported link/device in {purpose} archive: {member.name!r}"
                    )
                count += 1
                if member.isfile():
                    regular_file_bytes += member.size
            archive.extractall(target, members=members, filter="data")
    return count, regular_file_bytes


def validate_storage_archive(archive_path: Path) -> tuple[int, int]:
    """Backward-compatible name for storage archive validation tests."""
    return validate_archive(archive_path, purpose="storage")


def _record_history(
    root: Path,
    *,
    status: str,
    bundle: Path,
    details: str,
    **extra: object,
) -> None:
    try:
        append_history(
            root,
            event="restore-test",
            status=status,
            bundle_dir=bundle,
            details=details,
            **extra,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(f"WARNING: could not update backup history: {exc}", file=sys.stderr)


def _restore(
    bundle: Path,
    compose_file: Path,
    *,
    keep_database: bool,
    require_signature: bool,
    require_configuration: bool,
) -> tuple[int, str]:
    manifest = verify_bundle(bundle, require_signature=require_signature)
    print(f"Manifest/hash verification passed ({len(manifest['files'])} files).")
    with tempfile.TemporaryDirectory(prefix="finpilot-dr-decrypt-") as scratch_str:
        files = resolve_backup_files(bundle, manifest, Path(scratch_str))
        dump_path = files.get("database.dump")
        storage_path = files.get("storage.tar.gz")
        config_path = files.get("configuration.tar.gz")
        if dump_path is None:
            raise BackupVerificationError(
                "Bundle does not contain database.dump or database.dump.gpg"
            )
        if storage_path is None:
            raise BackupVerificationError(
                "Bundle does not contain storage.tar.gz or storage.tar.gz.gpg"
            )
        if require_configuration and config_path is None:
            raise BackupVerificationError(
                "Bundle does not contain configuration.tar.gz "
                "or configuration.tar.gz.gpg"
            )

        restore_db = "finpilot_dr_restore_test_" + datetime.now(UTC).strftime(
            "%Y%m%d%H%M%S"
        )
        database_created = False
        try:
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
                    '"SELECT version_num FROM alembic_version ORDER BY version_num"',
                    "sh",
                    restore_db,
                )
            )
            if not revision:
                raise RuntimeError("The restored Alembic version table has no revision")

            storage_entries, storage_bytes = validate_archive(
                storage_path, purpose="storage"
            )
            if config_path is not None:
                config_entries, config_bytes = validate_archive(
                    config_path, purpose="configuration"
                )
                print(
                    "Configuration archive passed: "
                    f"{config_entries} entries; {config_bytes} uncompressed bytes."
                )
            elif not require_configuration:
                print("WARNING: legacy backup has no configuration archive.")

            formatted_revision = revision.replace("\n", ", ")
            print(
                f"Database restore passed: {tables} public tables; "
                f"Alembic revision(s): {formatted_revision}."
            )
            print(
                f"Storage archive passed: {storage_entries} entries; "
                f"{storage_bytes} uncompressed file bytes."
            )
            print(
                "NOTE: this is a technical restore test, not business-data, "
                "tenant-isolation, or full-service validation."
            )
            if keep_database:
                print(f"Throwaway restore-test database preserved: {restore_db}")
            else:
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
            return tables, revision
        except Exception:
            if database_created:
                print(
                    "Throwaway restore-test database left for inspection: "
                    f"{restore_db}",
                    file=sys.stderr,
                )
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle_dir", type=Path, help="Path to one finpilot-dr-* backup bundle"
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=ROOT / "docker" / "docker-compose.yml",
    )
    parser.add_argument(
        "--keep-database",
        action="store_true",
        help="Keep the throwaway database after a successful test",
    )
    parser.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail unless manifest.json.asc is present and valid",
    )
    parser.add_argument(
        "--require-configuration",
        action="store_true",
        help="Fail if the backup does not contain configuration.tar.gz",
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
    started = time.monotonic()
    try:
        tables, revision = _restore(
            bundle,
            compose_file,
            keep_database=args.keep_database,
            require_signature=require_signature,
            require_configuration=args.require_configuration,
        )
        _record_history(
            bundle.parent,
            status="success",
            bundle=bundle,
            details="Database, storage, and available configuration archives verified.",
            table_count=tables,
            alembic_revisions=revision.splitlines(),
            duration_seconds=round(time.monotonic() - started, 2),
        )
        return 0
    except (
        BackupVerificationError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as exc:
        print(f"RESTORE TEST FAILED: {exc}", file=sys.stderr)
        _record_history(
            bundle.parent,
            status="failure",
            bundle=bundle,
            details=str(exc),
            duration_seconds=round(time.monotonic() - started, 2),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
