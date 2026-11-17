"""vanilla-diff (ROADMAP.md, "Game-build diff" 2026-11-15): two synthetic tiny game builds, no game files."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starsector_variant_generator.analysis import vanilla_diff
from starsector_variant_generator.cli import main as cli_main

HULL_HEADER = "name,id,hitpoints,armor rating,max flux,flux dissipation,ordnance points,max speed,hullSize,desc\n"
WEAPON_HEADER = "name,id,OPs,range,damage/shot,energy/shot,type,size,mountType\n"
MOD_HEADER = "name,id,cost_frigate,cost_dest,cost_cruiser,cost_capital,hidden\n"
WING_HEADER = "id,role,opCost,refit\n"
SYSTEM_HEADER = "name,id,cooldown,max uses,flux/second\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_install(root: Path, *, vent: int = 10, hulls: str, weapons: str, mods: str, wings: str, systems: str, system_json: str = '{"id": "synth_sys", "range": 500}') -> Path:
    core = root / "starsector-core"
    write(core / "data/hulls/ship_data.csv", HULL_HEADER + hulls)
    write(core / "data/weapons/weapon_data.csv", WEAPON_HEADER + weapons)
    write(core / "data/hullmods/hull_mods.csv", MOD_HEADER + mods)
    write(core / "data/hulls/wing_data.csv", WING_HEADER + wings)
    write(core / "data/shipsystems/ship_systems.csv", SYSTEM_HEADER + systems)
    write(core / "data/shipsystems/synth_sys.system", system_json)
    write(core / "data/config/settings.json", f'{{"dissipationPerVent": {vent}, "fluxPerCapacitor": 200, "maxLogisticsHullmods": 2}}')
    return root


OLD = dict(
    hulls="Synth Frigate,synth_frigate,1000,100,3000,200,40,120,FRIGATE,old text\nSynth Gone,synth_gone,800,50,1000,100,20,90,FRIGATE,x\n",
    weapons="Synth Gun,synth_gun,10,600,100,50,KINETIC,SMALL,TURRET\n",
    mods="Synth Mod,synth_mod,5,10,15,25,\n",
    wings="synth_wing,BOMBER,10,5\n",
    systems="Synth Sys,synth_sys,5,2,\n",
)
NEW = dict(
    hulls="Synth Frigate,synth_frigate,1200,100,3000,200,35,120,FRIGATE,new text\nSynth New,synth_new,700,40,900,90,18,80,FRIGATE,y\n",
    weapons="Synth Gun,synth_gun,10,750,100,50,KINETIC,SMALL,TURRET\n",
    mods="Synth Mod,synth_mod,5,10,15,25,\n",
    wings="synth_wing,BOMBER,10,5\n",
    systems="Synth Sys,synth_sys,6,2,\n",
    system_json='{"id": "synth_sys", "range": 700}',
)


class VanillaDiffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.old = build_install(self.base / "old", **OLD)
        self.new = build_install(self.base / "new", vent=12, **NEW)
        self.refs = self.base / "refs"
        write(self.refs / "pack.json", '{"hulls": ["synth_gone", "synth_new"], "weapon": "synth_gun", "other": "synth_frigate_extra"}')
        write(self.refs / "untouched.json", '{"hull": "synth_other"}')

    def report(self) -> dict:
        return vanilla_diff.build_report(self.old, self.new, reference_roots=[self.refs])

    def test_hulls_report_added_removed_and_changed_fields(self) -> None:
        hulls = self.report()["kinds"]["hulls"]
        self.assertEqual([e["id"] for e in hulls["added"]], ["synth_new"])
        self.assertEqual([e["id"] for e in hulls["removed"]], ["synth_gone"])
        changes = {c["field"]: c for c in hulls["changed"][0]["changes"]}
        self.assertEqual((changes["hitpoints"]["old"], changes["hitpoints"]["new"]), ("1000", "1200"))
        self.assertEqual(changes["ordnance points"]["relative"], round(-5 / 40, 4))
        self.assertNotIn("desc", changes)
        self.assertNotIn("max flux", changes)

    def test_weapons_systems_and_unchanged_kinds(self) -> None:
        report = self.report()
        weapon = report["kinds"]["weapons"]["changed"][0]
        self.assertEqual((weapon["id"], weapon["changes"][0]["field"]), ("synth_gun", "range"))
        system_fields = {c["field"] for c in report["kinds"]["shipsystems"]["changed"][0]["changes"]}
        self.assertEqual(system_fields, {"cooldown", "system.range"})
        for kind in ("hullmods", "fighters"):
            self.assertEqual(report["summary"][kind], {"old": 1, "new": 1, "added": 0, "removed": 0, "changed": 0})

    def test_settings_flag_changes_and_hardcoded_mismatch(self) -> None:
        rows = {row["key"]: row for row in self.report()["settings"]}
        vent = rows["dissipationPerVent"]
        self.assertTrue(vent["changed"])
        self.assertTrue(vent["new_differs_from_hardcoded"])
        self.assertFalse(rows["fluxPerCapacitor"]["changed"])
        self.assertFalse(rows["fluxPerCapacitor"]["new_differs_from_hardcoded"])
        self.assertIn("note", rows["max vents / capacitors per hull size"])

    def test_affects_voidsmith_lists_file_and_whole_token_ids_only(self) -> None:
        hits = self.report()["affects_voidsmith"]["hits"]
        self.assertEqual([h["file"] for h in hits], ["refs/pack.json"])
        named = {i["id"]: i["kinds"] for i in hits[0]["ids"]}
        self.assertEqual(named["synth_gone"], {"hulls": "removed"})
        self.assertEqual(named["synth_gun"], {"weapons": "changed"})
        self.assertNotIn("synth_frigate", named)  # only `synth_frigate_extra` appears: not a whole-token match
        self.assertNotIn("synth_new", named)  # added entities cannot be stale

    def test_largest_changes_sorted_by_relative_size(self) -> None:
        top = self.report()["largest_changes"]
        self.assertEqual([abs(r["relative"]) for r in top], sorted((abs(r["relative"]) for r in top), reverse=True))

    def test_markdown_has_every_section(self) -> None:
        text = vanilla_diff.to_markdown(self.report())
        for heading in ("## Summary", "## Settings VoidSmith reads or hard-codes", "## hulls", "## Affects VoidSmith"):
            self.assertIn(heading, text)
        self.assertIn("hitpoints: 1000 -> 1200", text)

    def test_install_without_data_folder_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            vanilla_diff.build_report(self.base / "missing", self.new)

    def test_cli_writes_json_and_leaves_installs_untouched(self) -> None:
        before = sorted(p.relative_to(self.base) for p in self.base.rglob("*"))
        out = self.base / "out" / "report.json"
        argv = ["voidsmith", "vanilla-diff", "--old", str(self.old), "--new", str(self.new), "--json", "--output", str(out), "--affects-path", str(self.refs)]
        with mock.patch("sys.argv", argv):
            code = cli_main.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["schema_version"], vanilla_diff.SCHEMA_VERSION)
        after = sorted(p.relative_to(self.base) for p in self.base.rglob("*") if "out" not in p.relative_to(self.base).parts)
        self.assertEqual(before, after)

    def test_cli_refuses_output_inside_an_install(self) -> None:
        argv = ["voidsmith", "vanilla-diff", "--old", str(self.old), "--new", str(self.new), "--output", str(self.new / "report.md")]
        with mock.patch("sys.argv", argv), self.assertRaises(SystemExit):
            cli_main.main()
        self.assertFalse((self.new / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
