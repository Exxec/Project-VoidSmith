from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Faction, Hull, Hullmod, ModInfo, ScanResult, SourceType, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.output.analysis_reports import write_scan_analysis_reports


SOURCE = Path("fixture")


class ScanAnalysisReportTests(unittest.TestCase):
    def test_reports_are_grouped_by_mod_and_include_mechanical_evidence(self) -> None:
        hull = Hull(
            "example_hull", "Example Hull", "example_mod", SOURCE,
            weapon_mounts=({"id": "M1", "type": "MISSILE", "size": "MEDIUM", "arc": 90},),
            hull_hints=("CIVILIAN", "FREIGHTER"), cargo_capacity=400,
        )
        weapon = Weapon("example_gun", "Example Gun", "example_mod", SOURCE, mount_type="BALLISTIC", range=1000)
        hullmod = Hullmod("example_modification", "Example Modification", "example_mod", SOURCE, hidden=True)
        faction = Faction("example_faction", "Example Faction", "example_mod", SOURCE, known_hulls=("example_hull",))
        variant = Variant("example_variant", "Example Variant", "example_mod", SOURCE, hull_id="example_hull", weapons_by_mount={"M1": "example_gun"})
        scan = ScanResult(hulls=[hull], weapons=[weapon], hullmods=[hullmod], factions=[faction], variants=[variant])
        registry = Registry.from_scan(scan)

        with tempfile.TemporaryDirectory() as temp:
            manifest = write_scan_analysis_reports(scan, registry, Path(temp), "baseline_0.3")
            capability = Path(temp) / "factions/example_faction_capability_profile.json"
            doctrine = Path(temp) / "factions/example_faction_doctrine_inference.json"
            hull_profile = Path(temp) / "hulls/example_hull_profile.json"
            weapons = Path(temp) / "equipment/weapon_profiles.json"
            hullmods = Path(temp) / "equipment/hullmod_profiles.json"
            hullmod_source_analysis = Path(temp) / "equipment/hullmod_source_analysis.json"
            self.assertEqual(2, len(manifest["faction_reports"]))
            self.assertTrue(all(path.exists() for path in (capability, doctrine, hull_profile, weapons, hullmods, hullmod_source_analysis)))
            profile = json.loads(hull_profile.read_text(encoding="utf-8"))
            self.assertIn("MISSILE_SUPPORT", profile["profile"]["compatibility_scores"])
            self.assertTrue(profile["profile"]["evidence_by_archetype"]["MISSILE_SUPPORT"])
            self.assertIn("MISSILE_PROJECTION", profile["capability_vector"]["dimensions"])
            weapon_profiles = json.loads(weapons.read_text(encoding="utf-8"))
            self.assertEqual("LONG", weapon_profiles["profiles_by_mod"]["example_mod"][0]["classification"]["range_band"])
            self.assertIn("ARTILLERY", weapon_profiles["profiles_by_mod"]["example_mod"][0]["classification"]["role_tags"])
            hullmod_profiles = json.loads(hullmods.read_text(encoding="utf-8"))
            self.assertIn("HIDDEN", hullmod_profiles["profiles_by_mod"]["example_mod"][0]["classification"]["property_tags"])
            source_profiles = json.loads(hullmod_source_analysis.read_text(encoding="utf-8"))
            self.assertEqual("starsector-api-effects-0.4", source_profiles["api_effect_registry"])
            self.assertEqual("example_modification", source_profiles["hullmods"][0]["hullmod_id"])
            self.assertIn("example_mod", source_profiles["profiles_by_mod"])

    def test_duplicate_hull_ids_include_source_mod_in_filename(self) -> None:
        first = Hull("shared", "First", "mod_a", SOURCE)
        second = Hull("shared", "Second", "mod_b", SOURCE)
        scan = ScanResult(hulls=[first, second])
        with tempfile.TemporaryDirectory() as temp:
            write_scan_analysis_reports(scan, Registry.from_scan(scan), Path(temp), "baseline_0.3")
            self.assertTrue((Path(temp) / "hulls/mod_a_shared_profile.json").exists())
            self.assertTrue((Path(temp) / "hulls/mod_b_shared_profile.json").exists())

    def test_complete_unchanged_report_set_can_be_reused(self) -> None:
        hull = Hull("example", "Example", "example_mod", SOURCE, source_hash="fixture-source-hash")
        scan = ScanResult(hulls=[hull])
        with tempfile.TemporaryDirectory() as temp:
            reports = Path(temp)
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            reused = write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual("REUSED_UNCHANGED", reused["reuse_status"])

    def test_report_reuse_fails_closed_when_local_java_evidence_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "data/hullmods/hull_mods.csv"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("id\nexample\n", encoding="utf-8")
            java = root / "src/Example.java"
            java.parent.mkdir()
            java.write_text("class Example {}", encoding="utf-8")
            hullmod = Hullmod("example", "Example", "example_mod", source_path, source_hash="csv-hash")
            scan = ScanResult(
                mods=[ModInfo("example_mod", "Example", None, root, True, source_type=SourceType.MOD)],
                hullmods=[hullmod],
            )
            reports = root / "reports"
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            java.write_text("class Example { int changed; }", encoding="utf-8")
            rerun = write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual("RECOMPUTED", rerun["reuse_status"])

    def test_recomputed_hullmod_source_analysis_reflects_the_actual_new_java_content(self) -> None:
        # Reproduces a real bug: the outer manifest-hash check correctly
        # detects changed Java evidence and reports "RECOMPUTED" (proven by
        # the test above), but the recomputation itself used to be able to
        # silently reuse the FIRST call's Java file content via
        # hullmod_static_analysis.py::_java_sources -- an lru_cache keyed
        # only on the source-root path, with no invalidation of its own.
        # Both calls below resolve to the exact same source root, so this
        # would previously have written a "RECOMPUTED" report whose
        # recognized_effects still reflected the *original* (pre-edit) Java
        # file rather than the one actually on disk at write time.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "data/hullmods/hull_mods.csv"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("id\nexample\n", encoding="utf-8")
            java = root / "src/Example.java"
            java.parent.mkdir()
            java.write_text("class Example {}", encoding="utf-8")
            hullmod = Hullmod("example", "Example", "example_mod", source_path, source_hash="csv-hash", raw={"script": "Example"})
            scan = ScanResult(
                mods=[ModInfo("example_mod", "Example", None, root, True, source_type=SourceType.MOD)],
                hullmods=[hullmod],
            )
            reports = root / "reports"
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            first = json.loads((reports / "equipment/hullmod_source_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual([], first["hullmods"][0]["recognized_effects"])

            java.write_text(
                "class Example { void apply(MutableShipStatsAPI stats) { stats.getEnergyWeaponFluxCostMod().modifyPercent(id, -10f); } }",
                encoding="utf-8",
            )
            rerun = write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual("RECOMPUTED", rerun["reuse_status"])
            second = json.loads((reports / "equipment/hullmod_source_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual("energy_weapon_flux_cost", second["hullmods"][0]["recognized_effects"][0]["target_stat"])

    def test_unaffected_hull_profile_reuses_after_another_hull_changes(self) -> None:
        first = Hull("first", "First", "example_mod", SOURCE, source_hash="first-v1")
        second = Hull("second", "Second", "example_mod", SOURCE, source_hash="second-v1")
        scan = ScanResult(hulls=[first, second])
        with tempfile.TemporaryDirectory() as temp:
            reports = Path(temp)
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            changed_second = Hull("second", "Second Changed", "example_mod", SOURCE, source_hash="second-v2")
            changed_scan = ScanResult(hulls=[first, changed_second])
            manifest = write_scan_analysis_reports(changed_scan, Registry.from_scan(changed_scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual({"reused": 1, "recomputed": 1}, manifest["hull_profile_reuse"])

    def test_unaffected_faction_reports_reuse_after_other_faction_changes(self) -> None:
        hull = Hull("hull", "Hull", "mod_a", SOURCE, source_hash="hull-v1")
        first = Faction("first", "First", "mod_a", SOURCE, known_hulls=("hull",), source_hash="first-v1")
        second = Faction("second", "Second", "mod_b", SOURCE, source_hash="second-v1")
        scan = ScanResult(hulls=[hull], factions=[first, second])
        with tempfile.TemporaryDirectory() as temp:
            reports = Path(temp)
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            changed_second = Faction("second", "Second Changed", "mod_b", SOURCE, source_hash="second-v2")
            changed_scan = ScanResult(hulls=[hull], factions=[first, changed_second])
            manifest = write_scan_analysis_reports(changed_scan, Registry.from_scan(changed_scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual({"reused": 2, "recomputed": 2}, manifest["faction_report_reuse"])

    def test_unaffected_hullmod_source_fragment_reuses_after_other_mod_changes(self) -> None:
        first = Hullmod("first", "First", "mod_a", SOURCE, source_hash="first-v1")
        second = Hullmod("second", "Second", "mod_b", SOURCE, source_hash="second-v1")
        scan = ScanResult(hullmods=[first, second])
        with tempfile.TemporaryDirectory() as temp:
            reports = Path(temp)
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            changed_second = Hullmod("second", "Second Changed", "mod_b", SOURCE, source_hash="second-v2")
            changed_scan = ScanResult(hullmods=[first, changed_second])
            manifest = write_scan_analysis_reports(changed_scan, Registry.from_scan(changed_scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual({"reused_mods": 1, "recomputed_mods": 1}, manifest["hullmod_source_reuse"])

    def test_unaffected_weapon_profile_fragment_reuses_after_other_mod_changes(self) -> None:
        first = Weapon("first", "First", "mod_a", SOURCE, source_hash="first-v1")
        second = Weapon("second", "Second", "mod_b", SOURCE, source_hash="second-v1")
        scan = ScanResult(weapons=[first, second])
        with tempfile.TemporaryDirectory() as temp:
            reports = Path(temp)
            write_scan_analysis_reports(scan, Registry.from_scan(scan), reports, "baseline_0.3")
            changed_second = Weapon("second", "Second Changed", "mod_b", SOURCE, source_hash="second-v2")
            changed_scan = ScanResult(weapons=[first, changed_second])
            manifest = write_scan_analysis_reports(changed_scan, Registry.from_scan(changed_scan), reports, "baseline_0.3", reuse_if_unchanged=True)
            self.assertEqual(1, manifest["equipment_profile_reuse"]["weapon_reused_mods"])
            self.assertEqual(1, manifest["equipment_profile_reuse"]["weapon_recomputed_mods"])

    def test_source_effect_evidence_is_json_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src"
            source.mkdir()
            (source / "Speed.java").write_text(
                "class Speed { void apply(MutableShipStatsAPI stats) { stats.getMaxSpeed().modifyFlat(id, 20f); } }",
                encoding="utf-8",
            )
            hullmod = Hullmod("speed", "Speed", "example_mod", root / "data/hullmods/hull_mods.csv", raw={"script": "Speed"})
            write_scan_analysis_reports(ScanResult(hullmods=[hullmod]), Registry.from_scan(ScanResult(hullmods=[hullmod])), root / "reports", "baseline_0.3")
            report = json.loads((root / "reports/equipment/hullmod_source_analysis.json").read_text(encoding="utf-8"))
            self.assertEqual("HULLMOD_EFFECT", report["hullmods"][0]["evidence"][0]["evidence_type"])


if __name__ == "__main__":
    unittest.main()
