from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from starsector_variant_generator.analysis.release_verification import verify_portable_release


class ReleaseVerificationTests(unittest.TestCase):
    def _archive(self, directory: Path, *, corrupt_inventory: bool = False) -> Path:
        root = "VoidSmith-1.0.0-win-x64"
        payload = b"portable test application"
        manifest = {
            "schema_version": "voidsmith-portable-release-1", "product": "VoidSmith", "version": "1.0.0",
            "platform": "windows-x64", "files": [{"path": "VoidSmith.exe", "bytes": len(payload), "sha256": "0" * 64 if corrupt_inventory else hashlib.sha256(payload).hexdigest()}],
        }
        archive = directory / "VoidSmith-1.0.0-win-x64.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(f"{root}/VoidSmith.exe", payload)
            package.writestr(f"{root}/release-manifest.json", json.dumps(manifest))
        return archive

    def test_verifies_matching_inventory_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); archive = self._archive(directory)
            checksum = directory / f"{archive.name}.sha256"
            checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()} *{archive.name}\n", encoding="ascii")
            result = verify_portable_release(archive, checksum)
            self.assertTrue(result.passed)
            self.assertEqual(("MATCH", "MATCH", "windows-x64"), (result.checksum_status, result.inventory_status, result.platform))

    def test_reports_inventory_mismatch_without_extracting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = verify_portable_release(self._archive(Path(temp), corrupt_inventory=True))
            self.assertFalse(result.passed)
            self.assertEqual("MISMATCH", result.inventory_status)
            self.assertTrue(any("Inventory hash mismatch" in finding for finding in result.findings))

    def test_rejects_checksum_for_another_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); archive = self._archive(directory)
            checksum = directory / "checksum.sha256"
            checksum.write_text(f"{'0' * 64} *other.zip\n", encoding="ascii")
            self.assertEqual("INVALID", verify_portable_release(archive, checksum).checksum_status)

    def test_verifies_tar_gz_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); archive = directory / "VoidSmith-1.0.0-linux-x64.tar.gz"
            root, payload = "VoidSmith-1.0.0-linux-x64", b"linux portable test"
            manifest = {"schema_version": "voidsmith-portable-release-1", "product": "VoidSmith", "version": "1.0.0", "platform": "linux-x64", "files": [{"path": "VoidSmith", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}]}
            with tarfile.open(archive, "w:gz") as package:
                for name, data in ((f"{root}/VoidSmith", payload), (f"{root}/release-manifest.json", json.dumps(manifest).encode("utf-8"))):
                    entry = tarfile.TarInfo(name); entry.size = len(data); package.addfile(entry, io.BytesIO(data))
            self.assertTrue(verify_portable_release(archive).passed)
