"""Local unit tests for DR manifest and archive safety helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.disaster_recovery.manifest import (
    BackupVerificationError,
    verify_bundle,
    write_manifest,
)
from scripts.disaster_recovery.restore_test import validate_storage_archive


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

    def test_storage_archive_rejects_path_traversal(self) -> None:
        import io
        import tarfile

        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "malicious.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../outside.txt")
                payload = b"not safe"
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(RuntimeError):
                validate_storage_archive(archive)

    def test_storage_archive_round_trip_and_count(self) -> None:
        import tarfile

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
