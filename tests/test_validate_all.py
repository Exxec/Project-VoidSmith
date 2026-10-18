from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starsector_variant_generator import api
from starsector_variant_generator.analysis.validate_all import select_variants, to_markdown
from starsector_variant_generator.cli import main as cli_main
from starsector_variant_generator.core.models import Hull, ModInfo, ScanResult, Variant, Weapon

SOURCE = Path("fixture")


def synthetic_scan() -> ScanResult:
    hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=10,
                weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BALLISTIC"},))
    gun = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
    heavy = Weapon("heavy_gun", "Heavy", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=15)
    variants = [
        Variant("legal_v", "Legal", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}),
        Variant("missing_weapon_v", "Missing", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "no_such_gun"}),
        Variant("over_op_v", "Over", "extra_mod", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "heavy_gun"}),
        Variant("missing_mod_v", "ModMissing", "extra_mod", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("no_such_mod",)),
    ]
    mods = [ModInfo("extra_mod", "Extra", "1", Path("mods/extra"), True)]
    return ScanResult(mods=mods, hulls=[hull], weapons=[gun, heavy], variants=variants)


class ValidateAllTests(unittest.TestCase):
    def test_groups_by_code_and_mod_with_recorded_runtime_severity_only(self) -> None:
        report = api.run_validate_all(synthetic_scan())
        self.assertEqual(4, report["variants_validated"])
        by_code = report["by_code"]
        self.assertEqual("FATAL_AT_NEW_GAME", by_code["WEAPON_NOT_FOUND"]["runtime_severity"])
        self.assertEqual(["core:missing_weapon_v"], by_code["WEAPON_NOT_FOUND"]["variants"])
        self.assertEqual("DROPPED_SILENTLY", by_code["HULLMOD_NOT_FOUND"]["runtime_severity"])
        self.assertEqual("NOT_RECORDED", by_code["OP_EXCEEDED"]["runtime_severity"])
        self.assertEqual({"extra_mod": 1}, by_code["OP_EXCEEDED"]["mods"])
        self.assertEqual(1, report["by_mod"]["core"]["results"]["LEGAL"])
        self.assertEqual(3, report["results"]["ILLEGAL"])

    def test_source_selection_core_mod_and_unknown(self) -> None:
        scan = synthetic_scan()
        self.assertEqual(2, len(select_variants(scan, "core")))
        self.assertEqual(2, len(select_variants(scan, "mod:extra_mod")))
        with self.assertRaises(ValueError):
            select_variants(scan, "everything")

    def test_progress_fires_once_per_source_mod_in_order(self) -> None:
        seen: list[tuple[int, int, str, int]] = []
        api.run_validate_all(synthetic_scan(), on_source_done=lambda i, n, mod, count, _s: seen.append((i, n, mod, count)))
        self.assertEqual([(1, 2, "core", 2), (2, 2, "extra_mod", 2)], seen)

    def test_markdown_lists_codes_and_mods(self) -> None:
        text = to_markdown(api.run_validate_all(synthetic_scan()))
        self.assertIn("| WEAPON_NOT_FOUND | failure | FATAL_AT_NEW_GAME |", text)
        self.assertIn("| extra_mod |", text)

    def test_the_command_writes_both_reports_and_exits_nonzero_for_illegal(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = Path(tmp) / "out"
            argv = ["voidsmith", "validate-all", "--starsector-path", str(Path(tmp)), "--output-dir", str(out), "--quiet"]
            with mock.patch("sys.argv", argv), mock.patch("starsector_variant_generator.cli.automation_commands.Scanner") as scanner:
                scanner.return_value.scan.return_value = synthetic_scan()
                code = cli_main.main()
            self.assertEqual(1, code)
            data = json.loads((out / "reports" / "validate_all.json").read_text(encoding="utf-8"))
            self.assertEqual(4, data["variants_validated"])
            self.assertTrue((out / "reports" / "validate_all.md").is_file())


if __name__ == "__main__":
    unittest.main()
