"""
Create a verified FinPilot backup of PostgreSQL,
local documents, and configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from scripts.disaster_recovery.history import append_history
from scripts.disaster_recovery.manifest import verify_bundle, write_manifest

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


def _is_sensitive_env(path: Path) -> bool:
    name = path.name.lower()
    safe_suffixes = (".example", ".sample", ".template")
    if name in {".env.example", ".env.sample", ".env.template"}:
        return False
    if name.endswith(safe_suffixes):
        return False
    return name == ".env" or name.startswith(".env.")


def configuration_files(
    root: Path,
    compose_file: Path,
    *,
    include_sensitive: bool,
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Return a constrained allowlist of config files and sensitive files omitted."""
    candidates: set[Path] = set()
    explicit = [
        root / ".env.example",
        root / "pyproject.toml",
        root / "uv.lock",
        root / "docker" / "docker-compose.yml",
        root / "docker" / "docker-compose.yaml",
        root / "docker" / ".env.example",
        root / "backend" / "alembic.ini",
        root / "backend" / "pyproject.toml",
        root / "backend" / "uv.lock",
        root / "backend" / ".env.example",
        root / "backend" / "app" / "core" / "config.py",
        root / "backend" / "app" / "core" / "settings.py",
    ]
    candidates.update(
        path for path in explicit if path.is_file() and not path.is_symlink()
    )

    for base in (root / "docker", root / "backend"):
        if not base.is_dir():
            continue
        patterns = (
            "*compose*.yml",
            "*compose*.yaml",
            "*.yml",
            "*.yaml",
            "*.ini",
            "*.toml",
            "Dockerfile*",
        )
        for pattern in patterns:
            candidates.update(
                path
                for path in base.glob(pattern)
                if path.is_file() and not path.is_symlink()
            )

    config_dirs = (
        root / "config",
        root / "backend" / "config",
        root / "docker" / "config",
    )
    config_suffixes = {".ini", ".toml", ".yaml", ".yml", ".conf", ".example"}
    for config_dir in config_dirs:
        if not config_dir.is_dir():
            continue
        for path in config_dir.rglob("*"):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix.lower() in config_suffixes
            ):
                candidates.add(path)

    sensitive_seen: list[str] = []
    for parent in (root, root / "docker", root / "backend"):
        if not parent.is_dir():
            continue
        for path in parent.glob(".env*"):
            if not path.is_file() or not _is_sensitive_env(path):
                continue
            relative = path.relative_to(root).as_posix()
            if include_sensitive:
                candidates.add(path)
            else:
                sensitive_seen.append(relative)

    if compose_file.is_file() and compose_file not in candidates:
        try:
            compose_file.relative_to(root)
            candidates.add(compose_file)
        except ValueError:
            # An external Compose file is included under a neutral archive path below.
            pass

    mapped: list[tuple[Path, str]] = []
    for path in sorted(candidates):
        try:
            archive_name = path.relative_to(root).as_posix()
        except ValueError:
            continue
        mapped.append((path, archive_name))

    if compose_file.is_file():
        try:
            compose_file.relative_to(root)
        except ValueError:
            mapped.append((compose_file, "external/deployment/docker-compose.yml"))

    unique = {name: (path, name) for path, name in mapped}
    return (
        sorted(unique.values(), key=lambda item: item[1]),
        sorted(set(sensitive_seen)),
    )


def create_configuration_archive(
    bundle_dir: Path,
    *,
    compose_file: Path,
    include_sensitive: bool,
    root: Path = ROOT,
) -> tuple[Path, dict[str, object]]:
    archive_path = bundle_dir / "configuration.tar.gz"
    files, omitted_sensitive = configuration_files(
        root, compose_file, include_sensitive=include_sensitive
    )
    inventory: dict[str, object] = {
        "format_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "included_files": [name for _, name in files],
        "sensitive_environment_files_included": include_sensitive
        and any(_is_sensitive_env(path) for path, _ in files),
        "sensitive_environment_files_omitted": omitted_sensitive,
        "note": (
            "Database values such as audit rows are included in database.dump; "
            "secrets in environment files are archived only when GPG encryption "
            "is enabled."
        ),
    }
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for path, archive_name in files:
            archive.add(path, arcname=archive_name, recursive=False)
        payload = (json.dumps(inventory, indent=2) + "\n").encode("utf-8")
        info = tarfile.TarInfo("FINPILOT_CONFIGURATION_INVENTORY.json")
        info.size = len(payload)
        info.mtime = int(time.time())
        archive.addfile(info, BytesIO(payload))
    if archive_path.stat().st_size <= 0:
        raise RuntimeError("Configuration archive was empty")
    return archive_path, inventory


def encrypt_bundle_files(bundle_dir: Path, recipient: str) -> None:
    if shutil.which("gpg") is None:
        raise RuntimeError("BACKUP_GPG_RECIPIENT is set, but gpg is not installed")
    files = [
        path
        for path in bundle_dir.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "manifest.json.asc"}
    ]
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


def _safe_history(
    output_root: Path, *, event: str, status: str, **record: object
) -> None:
    try:
        append_history(output_root, event=event, status=status, **record)
    except (OSError, TypeError, ValueError) as exc:
        print(f"WARNING: could not update backup history: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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

    started = time.monotonic()
    output_root = args.output_root.expanduser().resolve()
    compose_file = args.compose_file.resolve()
    if not compose_file.is_file():
        parser.error(f"Compose file not found: {compose_file}")

    recipient = os.environ.get("BACKUP_GPG_RECIPIENT", "").strip()
    signing_key = os.environ.get("BACKUP_GPG_SIGNING_KEY", "").strip()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.environment == "production" and (not recipient or not signing_key):
        message = (
            "Production backups require BACKUP_GPG_RECIPIENT and "
            "BACKUP_GPG_SIGNING_KEY."
        )
        print(f"ERROR: {message}", file=sys.stderr)
        _safe_history(
            output_root,
            event="backup",
            status="failure",
            environment=args.environment,
            encrypted=bool(recipient),
            signed=bool(signing_key),
            details=message,
        )
        return 2

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = output_root / f"finpilot-dr-{stamp}"
    try:
        bundle_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        message = "Timestamp collision; retry after one second."
        print(f"ERROR: backup bundle already exists: {bundle_dir}", file=sys.stderr)
        _safe_history(
            output_root,
            event="backup",
            status="failure",
            environment=args.environment,
            bundle_dir=bundle_dir,
            details=message,
        )
        return 1

    try:
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
        for service, remote_path, command, output_name in jobs:
            run(compose(compose_file, "exec", "-T", service, "sh", "-lc", command))
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
                        compose_file,
                        "exec",
                        "-T",
                        service,
                        "rm",
                        "-f",
                        remote_path,
                    ),
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

        _, config_inventory = create_configuration_archive(
            bundle_dir,
            compose_file=compose_file,
            include_sensitive=bool(recipient),
        )
        if recipient:
            encrypt_bundle_files(bundle_dir, recipient)
        else:
            print(
                "WARNING: no GPG recipient configured; this bundle is not encrypted.",
                file=sys.stderr,
            )
            if config_inventory["sensitive_environment_files_omitted"]:
                print(
                    "Sensitive .env files were excluded from configuration.tar.gz "
                    "because GPG encryption is not enabled.",
                    file=sys.stderr,
                )

        manifest_path = write_manifest(
            bundle_dir,
            environment=args.environment,
            repository_commit=repository_commit(),
        )
        if signing_key:
            sign_manifest(manifest_path, signing_key)
        manifest = verify_bundle(
            bundle_dir, require_signature=args.environment == "production"
        )
        expected_files = ("database.dump", "storage.tar.gz", "configuration.tar.gz")
        for name in expected_files:
            if name not in manifest["files"] and f"{name}.gpg" not in manifest["files"]:
                raise RuntimeError(
                    f"Backup bundle is missing required scope file: {name}"
                )

        duration = round(time.monotonic() - started, 2)
        append_history(
            output_root,
            event="backup",
            status="success",
            environment=args.environment,
            bundle_dir=bundle_dir,
            encrypted=bool(recipient),
            signed=bool(signing_key),
            file_count=len(manifest["files"]),
            repository_commit=manifest.get("repository_commit"),
            duration_seconds=duration,
            details=(
                "Manifest hashes verified; database, storage, configuration, and "
                "database-resident audit tables included."
            ),
        )
        print(f"Backup bundle created: {bundle_dir}")
        print(f"Manifest: {manifest_path}")
        print(f"Backup verification passed ({len(manifest['files'])} files).")
        print(f"History: {output_root / 'history.jsonl'}")
        if not recipient:
            print(
                "WARNING: this bundle is not GPG-encrypted; suitable only for "
                "controlled non-production use."
            )
        print(
            "Off-site upload is not configured by this package; copy successful "
            "bundles to an approved off-site destination."
        )
        return 0
    except (subprocess.CalledProcessError, RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR: backup failed: {exc}", file=sys.stderr)
        if args.environment == "production":
            for partial in bundle_dir.iterdir():
                if partial.is_file() and not partial.name.endswith(".gpg"):
                    try:
                        partial.unlink()
                    except OSError:
                        print(
                            f"WARNING: could not remove plaintext partial {partial}",
                            file=sys.stderr,
                        )
        _safe_history(
            output_root,
            event="backup",
            status="failure",
            environment=args.environment,
            bundle_dir=bundle_dir,
            encrypted=bool(recipient),
            signed=bool(signing_key),
            duration_seconds=round(time.monotonic() - started, 2),
            details=str(exc),
        )
        print(f"Partial bundle retained for inspection: {bundle_dir}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
