from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

from starsector_variant_generator.analysis.release_chain import verify_release_chain
from starsector_variant_generator.core.spw_inventory import review_spw_inventory


class SisterInterchangeTests(unittest.TestCase):
    def test_builder_emits_hash_bound_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "release.zip"
            archive.write_bytes(b"candidate")
            evidence = root / "release.zip.release-chain.json"
            script = Path(__file__).resolve().parents[1] / "tools" / "build_release_evidence.py"
            result = subprocess.run([sys.executable, str(script), str(archive), "--output", str(evidence)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), payload["archive_sha256"])
            self.assertEqual("PASS", payload["gates"]["build"]["state"])
            self.assertEqual("NOT_RUN", payload["gates"]["live"]["state"])

    def test_spw_inventory_matching_and_changed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "mods" / "sample"
            folder.mkdir(parents=True)
            metadata = folder / "mod_info.json"
            metadata.write_text('{"id":"sample"}', encoding="utf-8")
            inventory = root.parent / f"{root.name}-identity.json"
            inventory.write_text(json.dumps({"schema_version": "spw-mod-inventory-1",
                "installation_path": str(root), "mods": [{"id": "sample", "relative_root": "mods/sample",
                "metadata_status": "OK", "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
                "enabled": True, "duplicate_id": False}]}), encoding="utf-8")
            self.assertEqual("MATCH", review_spw_inventory(inventory, root)["mods"][0]["state"])
            metadata.write_text('{"id":"changed"}', encoding="utf-8")
            self.assertEqual("UNKNOWN", review_spw_inventory(inventory, root)["mods"][0]["state"])
            inventory.unlink()

    def test_release_chain_needs_downloaded_asset_for_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "release.zip"
            archive.write_bytes(b"candidate")
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({"schema_version": "voidsmith-release-chain-1",
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "source": {"commit": "a" * 40, "clean": True},
                "gates": {"publication": {"state": "PASS", "evidence": "claimed", "date": "2026-09-27"}}}), encoding="utf-8")
            self.assertEqual("UNKNOWN", verify_release_chain(archive, evidence)["gates"]["publication"]["state"])
            downloaded = root / "downloaded.zip"
            downloaded.write_bytes(b"candidate")
            matching = verify_release_chain(archive, evidence, downloaded)
            self.assertEqual("UNKNOWN", matching["gates"]["publication"]["state"])
            self.assertTrue(matching["gates"]["publication"]["asset_bytes_match"])
            downloaded.write_bytes(b"different")
            self.assertEqual("FAIL", verify_release_chain(archive, evidence, downloaded)["gates"]["publication"]["state"])
