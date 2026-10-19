"""Integrity manifest helpers shared by the backup and restore-test tools."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

MANIFEST_NAME = "manifest.json"
SIGNATURE_NAME = "manifest.json.asc"


class BackupVerificationError(RuntimeError):
    """A backup bundle is missing data or failed integrity verification."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(
    bundle_dir: Path,
    *,
    environment: str,
    repository_commit: str | None,
) -> Path:
    """Create a manifest for regular files in the bundle except the manifest itself."""
    files: dict[str, dict[str, int | str]] = {}
    for path in sorted(bundle_dir.iterdir()):
        if not path.is_file() or path.name in {MANIFEST_NAME, SIGNATURE_NAME}:
            continue
        files[path.name] = {
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    if not files:
        raise BackupVerificationError("Cannot create a manifest for an empty bundle")

    manifest: dict[str, Any] = {
        "format_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "environment": environment,
        "repository_commit": repository_commit,
        "backup_kind": "postgresql_custom_dump_plus_storage_archive",
        "files": files,
    }
    manifest_path = bundle_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def verify_manifest_signature(bundle_dir: Path) -> bool:
    """Verify a detached GPG signature if present; return True when signed."""
    manifest_path = bundle_dir / MANIFEST_NAME
    signature_path = bundle_dir / SIGNATURE_NAME
    if not signature_path.exists():
        return False
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--verify", str(signature_path), str(manifest_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise BackupVerificationError(
            "This bundle has a signature, but GPG is not installed or not on PATH"
        ) from exc
    if result.returncode != 0:
        raise BackupVerificationError(
            "Manifest signature verification failed. "
            + (result.stderr.strip() or result.stdout.strip())
        )
    return True


def verify_bundle(
    bundle_dir: Path, *, require_signature: bool = False
) -> dict[str, Any]:
    """Verify the detached signature (if any) and every file hash in the manifest."""
    manifest_path = bundle_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise BackupVerificationError(f"Missing {MANIFEST_NAME} in {bundle_dir}")

    signed = verify_manifest_signature(bundle_dir)
    if require_signature and not signed:
        raise BackupVerificationError("A signed manifest is required for this restore")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupVerificationError("The backup manifest is not valid JSON") from exc

    if manifest.get("format_version") != 1:
        raise BackupVerificationError("Unsupported backup manifest format version")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise BackupVerificationError("The backup manifest has no file entries")

    for name, info in files.items():
        candidate = Path(name)
        if (
            candidate.is_absolute()
            or len(candidate.parts) != 1
            or candidate.name in {".", ".."}
        ):
            raise BackupVerificationError(f"Unsafe filename in manifest: {name!r}")
        if not isinstance(info, dict):
            raise BackupVerificationError(f"Invalid manifest entry for {name}")
        path = bundle_dir / name
        if not path.is_file():
            raise BackupVerificationError(f"Missing backup file: {name}")
        expected_hash = info.get("sha256")
        expected_size = info.get("size_bytes")
        if not isinstance(expected_hash, str) or not isinstance(expected_size, int):
            raise BackupVerificationError(f"Invalid digest/size for {name}")
        if path.stat().st_size != expected_size:
            raise BackupVerificationError(f"Size mismatch for {name}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise BackupVerificationError(f"SHA-256 mismatch for {name}")

    return cast(dict[str, Any], manifest)
