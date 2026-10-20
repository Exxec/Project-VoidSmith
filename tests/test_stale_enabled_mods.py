from __future__ import annotations

import json
import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.analysis.stale_enabled_mods import find_stale_enabled_mods, format_stale_line
from starsector_variant_generator.core.config import AppConfig
from starsector_variant_generator.analysis.acceptance_baseline import run_acceptance
from starsector_variant_generator.analysis.mod_acceptance import audit_mod_acceptance
from starsector_variant_generator.analysis.stale_enabled_mods import format_stale_entry, stale_enabled_entries
from starsector_variant_generator.core.models import ModInfo, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.core.scanner import enabled_mods_file

FIXTURES = Path(__file__).parent / "fixtures"


def _mod(mod_id: str, name: str, folder: str, enabled: bool | None) -> ModInfo:
    return ModInfo(mod_id, name, "1", Path("mods") / folder, enabled)


class StaleEnabledModTests(unittest.TestCase):
    def test_a_renamed_folder_is_suggested_with_the_matching_field(self) -> None:
        scan = ScanResult(skipped_entities=["Enabled mod not discovered: sample_pack"])
        installed = [_mod("sample_pack_v2", "Sample Pack Two", "Sample Pack V2", False), _mod("other", "Other", "Other", False)]
        (entry,) = find_stale_enabled_mods(scan, installed)
        self.assertEqual("sample_pack", entry.enabled_id)
        self.assertEqual("sample_pack_v2", entry.closest_mod_id)
        self.assertEqual("mod_id", entry.matched_field)
        self.assertGreaterEqual(entry.similarity or 0, 0.6)
        self.assertIn("never edited", format_stale_line(entry))

    def test_no_candidate_close_enough_leaves_the_suggestion_empty(self) -> None:
        scan = ScanResult(skipped_entities=["Enabled mod not discovered: zzzzqqqq"])
        (entry,) = find_stale_enabled_mods(scan, [_mod("alpha", "Alpha", "Alpha", False)])
        self.assertIsNone(entry.closest_mod_id)

    def test_already_enabled_mods_are_never_suggested(self) -> None:
        scan = ScanResult(skipped_entities=["Enabled mod not discovered: sample_pack"])
        (entry,) = find_stale_enabled_mods(scan, [_mod("sample_pack_v2", "Sample", "Sample", True)])
        self.assertIsNone(entry.closest_mod_id)

    def test_notes_about_other_things_are_ignored(self) -> None:
        scan = ScanResult(skipped_entities=["Malformed mod metadata skipped: x"])
        self.assertEqual([], find_stale_enabled_mods(scan, []))

    def test_the_scan_report_lists_a_stale_id_and_leaves_the_settings_file_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            shutil.copytree(FIXTURES / "game_install", root)
            shutil.copytree(FIXTURES / "vanilla_mod", root, dirs_exist_ok=True)
            settings = root / "settings.json"
            data = json.loads(settings.read_text(encoding="utf-8"))
            data["enabledMods"] = ["fixture_mod_old"]
            settings.write_text(json.dumps(data), encoding="utf-8")
            before = settings.read_bytes()
            out = Path(tmp) / "out"
            outcome = api.run_scan(AppConfig(root, out, out / "logs"), logging.getLogger("test-stale"))
            stale = outcome.report["stale_enabled_mods"]
            self.assertEqual(["fixture_mod_old"], [item["enabled_id"] for item in stale])
            self.assertEqual("fixture_mod", stale[0]["closest_mod_id"])
            self.assertEqual(before, settings.read_bytes())


class StaleEnabledAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scan = ScanResult(skipped_entities=[
            "Enabled mod not discovered: second_in_command",
            "Enabled mod not discovered: second_in_command",
            "Malformed mod metadata skipped: x/mod_info.json: bad",
        ])
        self.enabled_file = str(Path("game") / "mods" / "enabled_mods.json")

    def test_each_missing_id_is_listed_once_with_the_exact_id_and_file(self) -> None:
        entries = stale_enabled_entries(self.scan, self.enabled_file)
        self.assertEqual([{"mod_id": "second_in_command", "enabled_file": self.enabled_file,
                           "action": "remove this id from enabledMods"}], entries)

    def test_the_cli_line_names_the_id_and_the_file(self) -> None:
        (entry,) = stale_enabled_entries(self.scan, self.enabled_file)
        line = format_stale_entry(entry)
        self.assertIn('remove "second_in_command" from ' + self.enabled_file, line)
        self.assertIn("FAIL row is kept", line)

    def test_acceptance_audit_carries_stale_list_and_keeps_the_fail_row(self) -> None:
        audit = audit_mod_acceptance(self.scan, Registry.from_scan(self.scan), enabled_file=self.enabled_file)
        self.assertEqual(["second_in_command"], [item["mod_id"] for item in audit["stale_enabled"]])
        fail_rows = [record for record in audit["records"] if record["mod_id"] == "second_in_command"]
        self.assertEqual(["FAIL"], [record["classification"] for record in fail_rows])

    def test_run_acceptance_passes_the_file_into_the_report(self) -> None:
        audit = run_acceptance(self.scan, Registry.from_scan(self.scan), enabled_file=self.enabled_file)
        self.assertEqual(self.enabled_file, audit["stale_enabled"][0]["enabled_file"])

    def test_no_missing_ids_gives_an_empty_list(self) -> None:
        self.assertEqual([], stale_enabled_entries(ScanResult(), self.enabled_file))


class EnabledModsFileTests(unittest.TestCase):
    def test_the_enabled_mods_file_is_preferred_when_it_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mods").mkdir()
            (root / "mods" / "enabled_mods.json").write_text("{}", encoding="utf-8")
            (root / "settings.json").write_text("{}", encoding="utf-8")
            self.assertEqual(root / "mods" / "enabled_mods.json", enabled_mods_file(root))

    def test_settings_json_is_the_file_when_it_is_the_only_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "settings.json").write_text("{}", encoding="utf-8")
            self.assertEqual(root / "settings.json", enabled_mods_file(root))

    def test_missing_both_files_points_at_the_enabled_mods_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(Path(tmp) / "mods" / "enabled_mods.json", enabled_mods_file(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
