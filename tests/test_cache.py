from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.core.cache import update_manifest
from starsector_variant_generator.core.models import Hull, ScanResult


class CacheTests(unittest.TestCase):
    def test_manifest_detects_creation_change_and_stability(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            scan = ScanResult(hulls=[Hull("h", "Hull", "core", Path("hulls.csv"), source_hash="a")])
            self.assertEqual("CREATED", update_manifest(path, scan).status)
            self.assertEqual("UNCHANGED", update_manifest(path, scan).status)
            changed_scan = ScanResult(hulls=[Hull("h", "Hull", "core", Path("hulls.csv"), source_hash="b")])
            result = update_manifest(path, changed_scan)
            self.assertEqual("CHANGED", result.status)
            self.assertEqual(1, result.changed)


if __name__ == "__main__":
    unittest.main()
