from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator import api
from starsector_variant_generator.analysis.variant import analyze_variant
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.overrides import EntityOverride
from starsector_variant_generator.core.registry import Registry


class VariantAnalysisTests(unittest.TestCase):
    def test_analysis_preserves_legality_before_quality(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        analysis = analyze_variant(variant, Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant])))
        self.assertEqual("LEGAL", analysis.legality.result)
        self.assertEqual("EVALUATED", analysis.quality.status)
        self.assertEqual((), analysis.civilian_role_tags)
        self.assertIsNotNone(analysis.civilian_stats)
        self.assertIsNotNone(analysis.defense_stats)
        self.assertIsNotNone(analysis.mobility_stats)
        self.assertIsNotNone(analysis.flux_stats)
        self.assertIsNotNone(analysis.weapon_range_stats)

    def test_api_analyzes_explicit_user_editable_variant_without_registry_indexing(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        local = Variant("local", "Local", "USER_EDITABLE", Path("local"), hull_id="h", weapons_by_mount={"A": "w"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        analysis = api.run_analyze_variant_record(registry, local, "LINE_BRAWLER", "BALANCED")
        self.assertEqual("LEGAL", analysis.legality.result)

    def test_analysis_surfaces_adapter_derived_mobility_stats(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=10,
                    raw={"max speed": "60"}, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        injector = Hullmod("unstable_injector", "Injector", "core", Path("m"), op_cost_by_hull_size={"FRIGATE": 5})
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("unstable_injector",))
        analysis = analyze_variant(variant, Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[injector], variants=[variant])))
        self.assertEqual(85.0, analysis.mobility_stats.effective_values["max_speed"])

    def test_analysis_surfaces_derived_defense_stats_for_a_combat_hull(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=10,
                    raw={"armor rating": "300"}, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        armor_mod = Hullmod("heavyarmor", "Heavy Armor", "core", Path("m"), op_cost_by_hull_size={"FRIGATE": 8})
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("heavyarmor",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[armor_mod], variants=[variant]))
        analysis = analyze_variant(variant, registry)
        self.assertEqual(300.0, analysis.defense_stats.armor_rating_base)
        self.assertEqual(450.0, analysis.defense_stats.effective_armor_rating)
        self.assertEqual(("heavyarmor",), analysis.defense_stats.applied_effect_hullmod_ids)

    def test_analysis_surfaces_derived_flux_stats_for_a_combat_hull(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=10,
                    flux_dissipation=100.0, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        distributor = Hullmod("fluxdistributor", "Flux Distributor", "core", Path("m"), op_cost_by_hull_size={"FRIGATE": 4})
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("fluxdistributor",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[distributor], variants=[variant]))
        analysis = analyze_variant(variant, registry)
        self.assertEqual(100.0, analysis.flux_stats.flux_dissipation_base)
        self.assertEqual(130.0, analysis.flux_stats.effective_flux_dissipation)
        self.assertEqual(("fluxdistributor",), analysis.flux_stats.applied_effect_hullmod_ids)

    def test_analysis_surfaces_derived_weapon_range_stats_for_a_combat_hull(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="CRUISER", ordnance_points=10,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000.0)
        itu = Hullmod("targetingunit", "Integrated Targeting Unit", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 15})
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("targetingunit",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[itu], variants=[variant]))
        analysis = analyze_variant(variant, registry)
        self.assertEqual(1400.0, analysis.weapon_range_stats.effective_range_by_mount["A"])
        self.assertEqual(("targetingunit",), analysis.weapon_range_stats.applied_effect_hullmod_ids)

    def test_analysis_surfaces_civilian_role_and_derived_stats_for_a_civilian_hull(self) -> None:
        hull = Hull("freighter", "Freighter", "core", Path("h"), hull_size="FRIGATE", ordnance_points=10,
                    hull_hints=("CIVILIAN", "FREIGHTER"), cargo_capacity=40.0,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        cargo_mod = Hullmod("expanded_cargo_holds", "Expanded Cargo Holds", "core", Path("m"), op_cost_by_hull_size={"FRIGATE": 5})
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="freighter", weapons_by_mount={"A": "w"}, hullmods=("expanded_cargo_holds",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[cargo_mod], variants=[variant]))
        analysis = analyze_variant(variant, registry)
        self.assertEqual(("CIVILIAN", "FREIGHTER"), analysis.civilian_role_tags)
        self.assertEqual(70.0, analysis.civilian_stats.cargo_capacity)
        self.assertEqual(("expanded_cargo_holds",), analysis.civilian_stats.applied_effect_hullmod_ids)
        self.assertEqual(1, len(analysis.civilian_stats.civilian_maintenance_penalty_notes))

    def test_hull_role_override_adds_a_civilian_tag_a_mods_hints_column_lacks(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), ordnance_points=10, cargo_capacity=200.0,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        without_override = analyze_variant(variant, registry)
        self.assertEqual((), without_override.civilian_role_tags)
        self.assertFalse(without_override.civilian_role_tags_overridden)
        override = EntityOverride("h", ("CIVILIAN", "FREIGHTER"), None)
        with_override = analyze_variant(variant, registry, hull_role_override=override)
        self.assertEqual(("CIVILIAN", "FREIGHTER"), with_override.civilian_role_tags)
        self.assertTrue(with_override.civilian_role_tags_overridden)

    @staticmethod
    def _combat_hullmod_fixture():
        """Same construction as tests/test_scoring.py's own
        `_combat_hullmod_fixture`: a CRUISER hull with two ENERGY-mount
        weapons sized so targetingunit's real +40% CRUISER range bonus
        (only consulted under baseline_0.9+'s opt-in
        `combat_hullmod_adjustment_enabled` gate) moves range_coherence's
        raw spread of 300 (55.0, above range_mismatch_moderate but within
        range_mismatch_severe) to a hullmod-adjusted spread of 420 (25.0,
        past range_mismatch_severe) -- a difference large enough to
        unambiguously prove which heuristic_set was actually used to score
        this variant, not just rounding noise.
        """
        hull = Hull("h_combat", "Combat Hull", "core", Path("h"), ordnance_points=60, hull_size="CRUISER",
                    weapon_mounts=(
                        {"id": "A", "type": "ENERGY", "size": "SMALL"},
                        {"id": "B", "type": "ENERGY", "size": "SMALL"},
                    ))
        w1 = Weapon("w1_combat", "Weapon 1", "core", Path("w"), size="SMALL", mount_type="ENERGY", ordnance_points=5, range=500.0)
        w2 = Weapon("w2_combat", "Weapon 2", "core", Path("w"), size="SMALL", mount_type="ENERGY", ordnance_points=5, range=800.0)
        targetingunit = Hullmod("targetingunit", "Integrated Targeting Unit", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 15})
        variant = Variant("v_combat", "Variant", "core", Path("v"), hull_id="h_combat",
                          weapons_by_mount={"A": "w1_combat", "B": "w2_combat"}, hullmods=("targetingunit",))
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[w1, w2], hullmods=[targetingunit], variants=[variant]))
        return registry, variant

    def test_analyze_variant_forwards_the_real_heuristic_set_to_scoring(self) -> None:
        """analysis/variant.py::analyze_variant previously had no heuristic_set
        parameter at all and always scored with score_candidate's own
        "baseline_0.2" default, silently ignoring whatever heuristic_set a
        real caller (CLI's `svg analyze-variant`, GUI's Compare Before/After)
        was actually configured with. Prove the fix with an observable
        score difference, not just a passed-through string: under
        baseline_0.2 range_coherence stays 55.0 (raw ranges, the gate is
        absent); under baseline_0.9 it becomes 25.0 (hullmod-adjusted
        ranges, the gate is present).
        """
        registry, variant = self._combat_hullmod_fixture()
        stale_default = analyze_variant(variant, registry, "LINE_ARTILLERY")
        self.assertEqual(55.0, stale_default.quality.components["range_coherence"])
        under_baseline_0_2 = analyze_variant(variant, registry, "LINE_ARTILLERY", heuristic_set="baseline_0.2")
        self.assertEqual(55.0, under_baseline_0_2.quality.components["range_coherence"])
        under_baseline_0_9 = analyze_variant(variant, registry, "LINE_ARTILLERY", heuristic_set="baseline_0.9")
        self.assertEqual(25.0, under_baseline_0_9.quality.components["range_coherence"])

    def test_run_analyze_variant_forwards_the_real_heuristic_set_end_to_end(self) -> None:
        """End-to-end production-orchestration proof for the same gap: the
        real CLI/GUI-facing api.run_analyze_variant (which previously had no
        heuristic_set parameter at all) must reach this same observable
        difference, not just analyze_variant's own direct call.
        """
        registry, _ = self._combat_hullmod_fixture()
        under_baseline_0_2 = api.run_analyze_variant(registry, "v_combat", "LINE_ARTILLERY", "BALANCED", "baseline_0.2")
        self.assertEqual(55.0, under_baseline_0_2.quality.components["range_coherence"])
        under_baseline_0_9 = api.run_analyze_variant(registry, "v_combat", "LINE_ARTILLERY", "BALANCED", "baseline_0.9")
        self.assertEqual(25.0, under_baseline_0_9.quality.components["range_coherence"])
        self.assertTrue(any(
            "w1_combat range hullmod-adjusted for scoring: 500 -> 700." in line
            for line in under_baseline_0_9.quality.explanation
        ))


if __name__ == "__main__":
    unittest.main()
