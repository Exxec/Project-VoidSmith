from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.core.scanner import Scanner

FIXTURES = Path(__file__).parent / "fixtures"


def _write_dropped_mod(directory: Path, mod_id: str, hull_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": mod_id.title()}), encoding="utf-8")
    hulls_dir = directory / "data" / "hulls"
    hulls_dir.mkdir(parents=True, exist_ok=True)
    (hulls_dir / "ship_data.csv").write_text(
        f"hullId,hullName,hull_size,ordnance_points\n{hull_id},{hull_id.title()},FRIGATE,40\n", encoding="utf-8",
    )


class IncrementalModScanTests(unittest.TestCase):
    """`api.run_incremental_mod_scan` lets a drag-and-dropped mod join an
    already-scanned session immediately, without re-scanning the whole
    installation -- see gui/main_window.py's dropEvent, which uses this to
    incorporate a drop without requiring "Scan Installed Data" again."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp_dir.name) / "game"
        shutil.copytree(FIXTURES / "game_install", self.root)
        shutil.copytree(FIXTURES / "vanilla_mod", self.root, dirs_exist_ok=True)
        shutil.copytree(FIXTURES / "modded_mod", self.root / "mods/fixture_mod", dirs_exist_ok=True)
        output = Path(self.temp_dir.name) / "output"
        self.config = AppConfig(self.root, output, output / "logs")
        self.existing_result = Scanner(self.root, cache_dir=self.config.output_dir / "cache").scan()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_a_dropped_mod_is_merged_without_rescanning_the_rest(self) -> None:
        dropped = Path(self.temp_dir.name) / "dropped" / "NewMod"
        _write_dropped_mod(dropped, "new_mod", "new_hull")
        original_hull_count = len(self.existing_result.hulls)

        outcome = api.run_incremental_mod_scan(self.config, self.existing_result, (dropped,))

        self.assertEqual(("new_mod",), outcome.added_mod_ids)
        self.assertEqual((), outcome.skipped_mod_roots)
        self.assertEqual(original_hull_count + 1, len(outcome.result.hulls))
        self.assertIn("new_hull", {hull.id for hull in outcome.result.hulls})
        self.assertIn("new_hull", outcome.registry.hulls.by_id)
        # Every original hull is still present, untouched.
        original_ids = {hull.id for hull in self.existing_result.hulls}
        merged_ids = {hull.id for hull in outcome.result.hulls}
        self.assertTrue(original_ids.issubset(merged_ids))

    def test_existing_result_is_never_mutated(self) -> None:
        dropped = Path(self.temp_dir.name) / "dropped" / "NewMod2"
        _write_dropped_mod(dropped, "new_mod_2", "new_hull_2")
        original_hull_ids = [hull.id for hull in self.existing_result.hulls]
        original_mod_count = len(self.existing_result.mods)

        api.run_incremental_mod_scan(self.config, self.existing_result, (dropped,))

        self.assertEqual(original_hull_ids, [hull.id for hull in self.existing_result.hulls])
        self.assertEqual(original_mod_count, len(self.existing_result.mods))

    def test_a_path_without_mod_info_json_is_skipped_not_raised(self) -> None:
        not_a_mod = Path(self.temp_dir.name) / "not_a_mod"
        not_a_mod.mkdir()
        (not_a_mod / "readme.txt").write_text("hello", encoding="utf-8")

        outcome = api.run_incremental_mod_scan(self.config, self.existing_result, (not_a_mod,))

        self.assertEqual((), outcome.added_mod_ids)
        self.assertEqual((not_a_mod,), outcome.skipped_mod_roots)
        self.assertEqual(len(self.existing_result.hulls), len(outcome.result.hulls))

    def test_a_dropped_mod_reusing_an_existing_hull_id_is_caught_as_a_real_duplicate(self) -> None:
        existing_hull_id = self.existing_result.hulls[0].id
        dropped = Path(self.temp_dir.name) / "dropped" / "Colliding"
        _write_dropped_mod(dropped, "colliding_mod", existing_hull_id)

        outcome = api.run_incremental_mod_scan(self.config, self.existing_result, (dropped,))

        self.assertIn(existing_hull_id, outcome.registry.hulls.duplicates)
        self.assertNotIn(existing_hull_id, outcome.registry.hulls.by_id)

    def test_multiple_dropped_mods_in_one_call_are_all_merged(self) -> None:
        first = Path(self.temp_dir.name) / "dropped" / "First"
        second = Path(self.temp_dir.name) / "dropped" / "Second"
        _write_dropped_mod(first, "first_mod", "first_hull")
        _write_dropped_mod(second, "second_mod", "second_hull")

        outcome = api.run_incremental_mod_scan(self.config, self.existing_result, (first, second))

        self.assertEqual({"first_mod", "second_mod"}, set(outcome.added_mod_ids))
        self.assertIn("first_hull", outcome.registry.hulls.by_id)
        self.assertIn("second_hull", outcome.registry.hulls.by_id)
