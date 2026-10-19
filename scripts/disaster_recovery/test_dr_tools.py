"""Unit tests for backup manifests, configuration scope, history, and archive safety."""

from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from scripts.disaster_recovery.automation import latest_bundle
from scripts.disaster_recovery.backup import create_configuration_archive
from scripts.disaster_recovery.history import append_history, read_history
from scripts.disaster_recovery.manifest import (
    BackupVerificationError,
    verify_bundle,
    write_manifest,
)
from scripts.disaster_recovery.restore_test import (
    validate_archive,
    validate_storage_archive,
)


class ManifestTests(unittest.TestCase):
    def test_manifest_verifies_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "database.dump").write_bytes(b"sample database dump")
            (bundle / "storage.tar.gz").write_bytes(b"sample archive bytes")
            write_manifest(bundle, environment="testing", repository_commit="deadbeef")
            manifest = verify_bundle(bundle)
            self.assertEqual(manifest["repository_commit"], "deadbeef")
            self.assertEqual(len(manifest["files"]), 2)

    def test_modified_file_fails_hash_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "database.dump").write_bytes(b"original")
            write_manifest(bundle, environment="testing", repository_commit=None)
            (bundle / "database.dump").write_bytes(b"modified")
            with self.assertRaises(BackupVerificationError):
                verify_bundle(bundle)

    def test_manifest_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "safe.bin").write_bytes(b"x")
            manifest = {
                "format_version": 1,
                "files": {"../outside.bin": {"size_bytes": 1, "sha256": "bad"}},
            }
            (bundle / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(BackupVerificationError):
                verify_bundle(bundle)

    def test_signature_can_be_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "database.dump").write_bytes(b"sample")
            write_manifest(bundle, environment="production", repository_commit=None)
            with self.assertRaises(BackupVerificationError):
                verify_bundle(bundle, require_signature=True)


class ConfigurationArchiveTests(unittest.TestCase):
    def _make_repo(self, root: Path) -> Path:
        (root / "docker").mkdir(parents=True)
        (root / "backend").mkdir()
        (root / "docker" / "docker-compose.yml").write_text(
            "services: {}\n", encoding="utf-8"
        )
        (root / "backend" / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
        (root / ".env.example").write_text("DB_NAME=example\n", encoding="utf-8")
        (root / ".env").write_text(
            "DB_PASSWORD=not-for-unencrypted-backup\n", encoding="utf-8"
        )
        return root / "docker" / "docker-compose.yml"

    def test_configuration_archive_excludes_active_env_without_encryption(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compose = self._make_repo(root)
            bundle = root / "bundle"
            bundle.mkdir()
            archive, inventory = create_configuration_archive(
                bundle,
                compose_file=compose,
                include_sensitive=False,
                root=root,
            )
            self.assertIn(
                "docker/docker-compose.yml",
                cast(Iterable[Any], inventory["included_files"]),
            )
            self.assertIn(
                ".env",
                cast(Iterable[Any], inventory["sensitive_environment_files_omitted"]),
            )
            with tarfile.open(archive, "r:gz") as tar:
                names = tar.getnames()
                self.assertIn(".env.example", names)
                self.assertNotIn(".env", names)
                self.assertIn("FINPILOT_CONFIGURATION_INVENTORY.json", names)

    def test_configuration_archive_includes_active_env_when_encryption_enabled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compose = self._make_repo(root)
            bundle = root / "bundle"
            bundle.mkdir()
            archive, inventory = create_configuration_archive(
                bundle,
                compose_file=compose,
                include_sensitive=True,
                root=root,
            )
            self.assertTrue(inventory["sensitive_environment_files_included"])
            with tarfile.open(archive, "r:gz") as tar:
                self.assertIn(".env", tar.getnames())


class HistoryTests(unittest.TestCase):
    def test_history_appends_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            history_path = append_history(
                root,
                event="backup",
                status="success",
                bundle_dir=root / "finpilot-dr-example",
                encrypted=False,
            )
            append_history(
                root,
                event="restore-test",
                status="failure",
                details="sample failure",
            )
            self.assertTrue(history_path.is_file())
            all_records = read_history(root, limit=5)
            self.assertEqual(len(all_records), 2)
            self.assertEqual(
                read_history(root, limit=5, event="backup")[0]["status"],
                "success",
            )

    def test_history_invalid_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "history.jsonl").write_text("not-json\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_history(root)


class AutomationTests(unittest.TestCase):
    def test_latest_bundle_requires_database_storage_and_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "finpilot-dr-old"
            new = root / "finpilot-dr-new"
            old.mkdir()
            new.mkdir()
            expected_names = (
                "database.dump",
                "storage.tar.gz",
                "configuration.tar.gz",
            )
            for directory, created_at in (
                (old, "2026-10-18T00:00:00+00:00"),
                (new, "2026-10-19T00:00:00+00:00"),
            ):
                for name in expected_names:
                    (directory / name).write_bytes(b"sample")
                (directory / "manifest.json").write_text(
                    json.dumps(
                        {
                            "created_at_utc": created_at,
                            "files": {
                                name: {"size_bytes": 6, "sha256": "placeholder"}
                                for name in expected_names
                            },
                        }
                    ),
                    encoding="utf-8",
                )
            self.assertEqual(latest_bundle(root), new)

    def test_latest_bundle_ignores_legacy_bundle_missing_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "finpilot-dr-legacy"
            legacy.mkdir()
            (legacy / "manifest.json").write_text(
                json.dumps(
                    {
                        "created_at_utc": "2026-10-19T00:00:00+00:00",
                        "files": {"database.dump": {}, "storage.tar.gz": {}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(FileNotFoundError):
                latest_bundle(root)


class ArchiveSafetyTests(unittest.TestCase):
    def test_storage_archive_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "malicious.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../outside.txt")
                payload = b"not safe"
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(RuntimeError):
                validate_storage_archive(archive)

    def test_archive_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "link.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("symlink")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside"
                tar.addfile(info)
            with self.assertRaises(RuntimeError):
                validate_archive(archive)

    def test_storage_archive_round_trip_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "sample.txt").write_text("restored evidence", encoding="utf-8")
            archive = root / "storage.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(source / "sample.txt", arcname="sample.txt")
            count, size = validate_storage_archive(archive)
            self.assertGreaterEqual(count, 1)
            self.assertEqual(size, len("restored evidence"))


if __name__ == "__main__":
    unittest.main()
