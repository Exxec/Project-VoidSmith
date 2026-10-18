from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starsector_variant_generator.cli import main as cli_main

FIXTURES = Path(__file__).parent / "fixtures"
GOOD = {"variantId": "mine_good", "displayName": "Good", "hullId": "fixture_frigate", "hullMods": [], "wings": [],
        "weaponGroups": [{"weapons": {"WS 001": "fixture_gun"}}]}


class CheckModTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.game = base / "game"
        shutil.copytree(FIXTURES / "game_install", self.game)
        shutil.copytree(FIXTURES / "vanilla_mod", self.game, dirs_exist_ok=True)
        (self.game / "mods" / "fixture_mod" / "mod_info.json").unlink()  # nothing from the installed mods is needed
        shutil.rmtree(self.game / "mods" / "fixture_mod")
        self.mod = base / "work" / "mine"
        (self.mod / "data" / "variants").mkdir(parents=True)
        (self.mod / "mod_info.json").write_text(json.dumps({"id": "mine", "name": "Mine", "version": "1"}), encoding="utf-8")
        self.out = base / "out"
        self.verdict_file = base / "verdict.json"

    def variant(self, name: str, payload: object | str) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (self.mod / "data" / "variants" / f"{name}.variant").write_text(text, encoding="utf-8")

    def run_cli(self, *extra: str) -> tuple[int, dict]:
        argv = ["voidsmith", "check-mod", str(self.mod), "--starsector-path", str(self.game), "--output-dir", str(self.out),
                "--output", str(self.verdict_file), *extra]
        with mock.patch("sys.argv", argv):
            code = cli_main.main()
        return code, json.loads(self.verdict_file.read_text(encoding="utf-8"))

    def snapshot(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.mod)): p.read_bytes() for p in self.mod.rglob("*") if p.is_file()}

    def test_a_clean_mod_passes_and_the_mod_folder_is_untouched(self) -> None:
        self.variant("good", GOOD)
        before = self.snapshot()
        code, verdict = self.run_cli()
        self.assertEqual((0, "PASS"), (code, verdict["verdict"]))
        self.assertEqual("mine", verdict["mod"]["id"])
        self.assertEqual(1, verdict["entity_counts"]["variants"])
        self.assertEqual(before, self.snapshot())

    def test_a_missing_weapon_fails_with_the_recorded_runtime_severity(self) -> None:
        self.variant("bad", {**GOOD, "variantId": "mine_bad", "weaponGroups": [{"weapons": {"WS 001": "no_such_gun"}}]})
        code, verdict = self.run_cli()
        self.assertEqual((2, "FAIL"), (code, verdict["verdict"]))
        self.assertEqual("FATAL_AT_NEW_GAME", verdict["validate_all"]["by_code"]["WEAPON_NOT_FOUND"]["runtime_severity"])

    def test_a_malformed_variant_fails_and_is_located(self) -> None:
        self.variant("good", GOOD)
        self.variant("broken", '{"variantId": "a"}\n{"variantId": "b"}\n')
        code, verdict = self.run_cli()
        self.assertEqual((2, "FAIL"), (code, verdict["verdict"]))
        self.assertEqual("CONCATENATED_VALUES", verdict["parse_failures"][0]["structure_issue"])

    def test_a_missing_hull_mod_is_review_not_fail(self) -> None:
        self.variant("mods", {**GOOD, "variantId": "mine_mods", "hullMods": ["no_such_mod"]})
        code, verdict = self.run_cli()
        self.assertEqual((1, "REVIEW"), (code, verdict["verdict"]))
        self.assertEqual("DROPPED_SILENTLY", verdict["validate_all"]["by_code"]["HULLMOD_NOT_FOUND"]["runtime_severity"])

    def test_the_verdict_cannot_be_written_inside_the_mod_folder(self) -> None:
        self.variant("good", GOOD)
        argv = ["voidsmith", "check-mod", str(self.mod), "--starsector-path", str(self.game), "--output-dir", str(self.out),
                "--output", str(self.mod / "verdict.json")]
        with mock.patch("sys.argv", argv), self.assertRaises(SystemExit):
            cli_main.main()
        self.assertFalse((self.mod / "verdict.json").exists())

    def test_a_folder_without_mod_info_fails(self) -> None:
        (self.mod / "mod_info.json").unlink()
        self.variant("good", GOOD)
        code, verdict = self.run_cli()
        self.assertEqual((2, "FAIL"), (code, verdict["verdict"]))
        self.assertIsNone(verdict["mod"]["id"])


if __name__ == "__main__":
    unittest.main()
