"""Synthetic SPW inventory round trip (docs/AUTOMATION_PLAN.md V4.2).

An inventory describing a neutral synthetic install is written the way the sister program writes one (schema
spw-mod-inventory-1), joined with VoidSmith's own scan through `api.run_scan(spw_inventory=...)`, and every ambiguous case must
leave the scan and its entities unchanged and say why. The recorded run on a real install is a local step (ROADMAP).
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.core.config import AppConfig

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = "spw-mod-inventory-1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SpwRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "game"
        shutil.copytree(FIXTURES / "game_install", self.root)
        shutil.copytree(FIXTURES / "vanilla_mod", self.root, dirs_exist_ok=True)
        self.out = base / "out"
        self.inventory_path = base / "inventory.json"
        self.mod_dir = self.root / "mods" / "fixture_mod"
        self.info = self.mod_dir / "mod_info.json"

    def record(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {"id": "fixture_mod", "relative_root": "mods/fixture_mod", "metadata_status": "OK",
                                   "metadata_sha256": sha(self.info), "enabled": True, "duplicate_id": False}
        return {**base, **overrides}

    def write_inventory(self, mods: list[dict[str, object]], **top: object) -> None:
        enabled = self.root / "mods" / "enabled_mods.json"
        payload = {"schema_version": SCHEMA, "installation_path": str(self.root),
                   "enabled_mods_sha256": sha(enabled) if enabled.is_file() else None, "mods": mods, **top}
        self.inventory_path.write_text(json.dumps(payload), encoding="utf-8")

    def scan(self, with_inventory: bool) -> api.ScanOutcome:
        config = AppConfig(self.root, self.out, self.out / "logs")
        return api.run_scan(config, logging.getLogger("test-spw"), spw_inventory=self.inventory_path if with_inventory else None)

    def states(self, outcome: api.ScanOutcome) -> dict[str, str]:
        context = outcome.report["spw_identity_context"]
        return {str(m["id"]): str(m["state"]) for m in context["mods"]}

    def test_exact_match_augments_provenance_and_changes_no_entity(self) -> None:
        self.write_inventory([self.record()])
        with_inventory, without = self.scan(True), self.scan(False)
        self.assertEqual({"fixture_mod": "MATCH"}, self.states(with_inventory))
        self.assertNotIn("spw_identity_context", without.report)
        for kind in ("hulls", "weapons", "variants", "factions"):
            self.assertEqual([e.id for e in getattr(without.result, kind)], [e.id for e in getattr(with_inventory.result, kind)])
        self.assertEqual(without.report["counts"], with_inventory.report["counts"])

    def test_changed_metadata_hash_is_unknown_with_a_reason(self) -> None:
        self.write_inventory([self.record(metadata_sha256="0" * 64)])
        context = self.scan(True).report["spw_identity_context"]
        self.assertEqual("UNKNOWN", context["mods"][0]["state"])
        self.assertIn("ambiguous", context["mods"][0]["reason"])

    def test_duplicate_ids_stay_unknown(self) -> None:
        self.write_inventory([self.record(), self.record(relative_root="mods/fixture_mod")])
        self.assertEqual({"fixture_mod": "UNKNOWN"}, self.states(self.scan(True)))
        self.write_inventory([self.record(duplicate_id=True)])
        self.assertEqual({"fixture_mod": "UNKNOWN"}, self.states(self.scan(True)))

    def test_a_disabled_metadata_rename_or_missing_metadata_is_unknown(self) -> None:
        self.write_inventory([self.record(metadata_status="DISABLED")])
        self.assertEqual({"fixture_mod": "UNKNOWN"}, self.states(self.scan(True)))
        self.write_inventory([self.record(id="ghost", relative_root="mods/ghost")])
        self.assertEqual({"ghost": "UNKNOWN"}, self.states(self.scan(True)))

    def test_a_stale_enabled_list_or_other_installation_is_reported_as_changed(self) -> None:
        (self.root / "mods" / "enabled_mods.json").write_text('{"enabledMods": ["fixture_mod"]}', encoding="utf-8")
        self.write_inventory([self.record()])
        (self.root / "mods" / "enabled_mods.json").write_text('{"enabledMods": []}', encoding="utf-8")
        self.assertEqual("CHANGED_INSTALLATION", self.scan(True).report["spw_identity_context"]["status"])
        self.write_inventory([self.record()], installation_path=str(self.root.parent / "elsewhere"))
        self.assertEqual("CHANGED_INSTALLATION", self.scan(True).report["spw_identity_context"]["status"])

    def test_unsafe_paths_and_wrong_schema_are_refused(self) -> None:
        self.write_inventory([self.record(relative_root="../outside")])
        with self.assertRaises(ValueError):
            self.scan(True)
        self.write_inventory([self.record()], schema_version="other")
        with self.assertRaises(ValueError):
            self.scan(True)


if __name__ == "__main__":
    unittest.main()
