from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.output.staleness import check_generation_manifest
from starsector_variant_generator.output.writer import (
    OutputCollisionError,
    write_compatibility_mod,
    write_variant,
)


class OutputTests(unittest.TestCase):
    def setUp(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        self.registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        self.variant = Variant("generated", "Generated", "generated", Path("generated"), hull_id="h", weapons_by_mount={"A": "w"})

    def test_writer_creates_variant_outside_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = write_variant(self.variant, self.registry, Path(temp))
            self.assertEqual("h", json.loads(path.read_text(encoding="utf-8"))["hullId"])

    def test_compatibility_mod_contains_only_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = write_compatibility_mod(self.variant, self.registry, Path(temp))
            self.assertTrue(path.exists())
            self.assertTrue((Path(temp) / "Starsector Auto Variants/mod_info.json").exists())
            manifest = Path(temp) / "Starsector Auto Variants/data/metadata/generation_manifest_generated.json"
            self.assertEqual("generated", json.loads(manifest.read_text(encoding="utf-8"))["variant_id"])
            self.assertEqual("baseline_0.1", json.loads(manifest.read_text(encoding="utf-8"))["heuristic_set"])
            self.assertEqual("LINE_BRAWLER", json.loads(manifest.read_text(encoding="utf-8"))["profile_id"])
            self.assertEqual("UNRESTRICTED", json.loads(manifest.read_text(encoding="utf-8"))["faction_mode"])
            self.assertEqual([{"source_mod": "core", "source_mod_version": None}], json.loads(manifest.read_text(encoding="utf-8"))["source_provenance_dependencies"])
            self.assertFalse(check_generation_manifest(manifest, self.registry).stale)

    def test_staleness_rejects_incomplete_or_changed_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(json.dumps({"hull_id": "h"}), encoding="utf-8")
            incomplete = check_generation_manifest(manifest, self.registry)
            self.assertTrue(incomplete.stale)
            self.assertIn("source_hull_hash", " ".join(incomplete.reasons))

            manifest.write_text(json.dumps({
                "generated_by": "test",
                "generator_version": "0",
                "variant_id": "generated",
                "generated_timestamp": "2026-08-21T00:00:00+00:00",
                "hull_id": "h",
                "profile_id": "LINE_BRAWLER",
                "faction_mode": "UNRESTRICTED",
                "source_hull_hash": "outdated",
                "source_weapon_hashes": {"w": "outdated"},
                "source_provenance_dependencies": [{"source_mod": "core", "source_mod_version": None}],
                "heuristic_set": "baseline_0.1",
                "resolved_heuristics": {},
            }), encoding="utf-8")
            changed = check_generation_manifest(manifest, self.registry)
            self.assertTrue(changed.stale)
            self.assertEqual(2, len(changed.reasons))

    def test_unknown_heuristic_set_creates_no_export_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Unknown heuristic set"):
                write_compatibility_mod(self.variant, self.registry, Path(temp), "invented_9.9")
            self.assertFalse((Path(temp) / "Starsector Auto Variants").exists())

    def test_differing_existing_variant_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "generated.variant"
            path.write_text('{"user": "edited"}', encoding="utf-8")
            with self.assertRaisesRegex(OutputCollisionError, "Refusing to overwrite"):
                write_variant(self.variant, self.registry, Path(temp))
            self.assertEqual('{"user": "edited"}', path.read_text(encoding="utf-8"))

    def test_identical_export_is_idempotent_but_changed_manifest_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            write_compatibility_mod(self.variant, self.registry, Path(temp))
            write_compatibility_mod(self.variant, self.registry, Path(temp))
            manifest = Path(temp) / "Starsector Auto Variants/data/metadata/generation_manifest_generated.json"
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw["profile_id"] = "USER_EDIT"
            manifest.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(OutputCollisionError, "differing existing manifest"):
                write_compatibility_mod(self.variant, self.registry, Path(temp))


if __name__ == "__main__":
    unittest.main()
