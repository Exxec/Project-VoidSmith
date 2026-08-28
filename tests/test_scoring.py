from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Faction, Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.scoring.candidate_score import score_candidate


class ScoringTests(unittest.TestCase):
    def test_baseline_0_5_scores_documented_pd_coverage_only_for_pd_escort(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        pd = Weapon("pd", "PD", "core", Path("fixture"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500, raw={"tags": "pd"})
        variant = Variant("v", "Variant", "core", Path("fixture"), hull_id="h", weapons_by_mount={"A": "pd"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[pd], variants=[variant]))
        assessment = score_candidate(variant, registry, "PD_ESCORT", "baseline_0.5")
        self.assertEqual(100.0, assessment.components["pd_coverage"])
        self.assertNotIn("missile_pressure", assessment.components)

    def setUp(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=10, range=1000)
        self.registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))

    def test_legal_candidate_receives_explainable_score(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY")
        self.assertEqual("EVALUATED", assessment.status)
        self.assertIsNotNone(assessment.final_score)

    def test_weight_overrides_rebalance_the_final_score(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        default_assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY")
        overridden_assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY", weight_overrides={"weight_op_efficiency": 10.0})
        self.assertEqual(89.3, default_assessment.final_score)
        self.assertEqual(52.6, overridden_assessment.final_score)
        self.assertTrue(any("Scoring weight override(s) applied" in line for line in overridden_assessment.explanation))

    def test_weight_overrides_do_not_affect_baseline_0_1_scoring(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.1", weight_overrides={"weight_op_efficiency": 10.0})
        self.assertNotIn("Scoring weight override", " ".join(assessment.explanation))

    def test_illegal_candidate_is_not_scored(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="missing")
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY")
        self.assertEqual("NOT_EVALUATED", assessment.status)
        self.assertIsNone(assessment.final_score)

    def test_empty_but_legal_loadout_is_not_quality_recommended(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h")
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY")
        self.assertEqual("EVALUATED", assessment.status)
        self.assertEqual(0.0, assessment.final_score)
        self.assertIn("No installed weapons", assessment.explanation[0])

    def test_baseline_0_1_reproduces_the_original_three_component_formula(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.1")
        self.assertEqual({"range_coherence", "op_efficiency", "role_match"}, set(assessment.components))
        self.assertEqual(("Primary range spread: 0.", "Weapon OP: 10/20."), assessment.explanation)

    def test_missing_flux_data_is_excluded_from_the_score_not_penalized(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.2")
        self.assertNotIn("flux_sustainability", assessment.components)
        self.assertTrue(any("flux_sustainability is not evaluated" in line for line in assessment.explanation))
        self.assertIsNotNone(assessment.final_score)

    def test_flux_sustainability_is_scored_when_data_is_complete(self) -> None:
        hull = Hull("h2", "Hull", "core", Path("h"), ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},),
                    flux_dissipation=200.0, shield_upkeep=0.0)
        weapon = Weapon("w2", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=10, range=1000, flux_per_second=100.0)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon]))
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h2", weapons_by_mount={"A": "w2"})
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.2", flux_mode="BALANCED")
        self.assertIn("flux_sustainability", assessment.components)
        self.assertEqual(100.0, assessment.components["flux_sustainability"])

    def test_faction_doctrine_match_is_reported_only_when_a_faction_is_supplied(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        without_faction = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.2")
        self.assertNotIn("faction_doctrine_match", without_faction.components)
        self.assertTrue(any("No faction supplied" in line for line in without_faction.explanation))
        faction = Faction("f", "Faction", "core", Path("f"))
        with_faction_but_no_evidence = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.2", faction=faction)
        self.assertNotIn("faction_doctrine_match", with_faction_but_no_evidence.components)
        self.assertTrue(any("No usable doctrine evidence" in line for line in with_faction_but_no_evidence.explanation))

    def test_civilian_efficiency_is_silently_absent_for_a_variant_with_no_logistics_hullmods(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.2")
        self.assertNotIn("civilian_efficiency", assessment.components)
        self.assertFalse(any("civilian_efficiency" in line or "Civilian logistics" in line for line in assessment.explanation))

    def test_civilian_efficiency_is_scored_when_a_logistics_hullmod_effect_applies(self) -> None:
        hull = Hull("civ", "Civ Hull", "core", Path("h"), ordnance_points=20, hull_size="FRIGATE", cargo_capacity=40.0,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        cargo_mod = Hullmod("expanded_cargo_holds", "Expanded Cargo Holds", "core", Path("m"), op_cost_by_hull_size={"FRIGATE": 5})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[cargo_mod]))
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="civ", weapons_by_mount={"A": "w"}, hullmods=("expanded_cargo_holds",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.2")
        self.assertIn("civilian_efficiency", assessment.components)
        self.assertEqual(100.0, assessment.components["civilian_efficiency"])  # gain 30 / OP 5 = 6.0, exactly the reference value
        self.assertTrue(any("Civilian logistics OP-efficiency" in line for line in assessment.explanation))

    def test_civilian_efficiency_does_not_affect_baseline_0_1_scoring(self) -> None:
        hull = Hull("civ", "Civ Hull", "core", Path("h"), ordnance_points=20, hull_size="FRIGATE", cargo_capacity=40.0,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        cargo_mod = Hullmod("expanded_cargo_holds", "Expanded Cargo Holds", "core", Path("m"), op_cost_by_hull_size={"FRIGATE": 5})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[cargo_mod]))
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="civ", weapons_by_mount={"A": "w"}, hullmods=("expanded_cargo_holds",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.1")
        self.assertNotIn("civilian_efficiency", assessment.components)

    def test_survivability_is_silently_absent_for_a_variant_with_no_defense_hullmods(self) -> None:
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="h", weapons_by_mount={"A": "w"})
        assessment = score_candidate(variant, self.registry, "LINE_ARTILLERY", "baseline_0.2")
        self.assertNotIn("survivability", assessment.components)
        self.assertFalse(any("survivability" in line or "Defense hullmod" in line for line in assessment.explanation))

    def test_survivability_is_scored_when_a_defense_hullmod_effect_applies(self) -> None:
        # heavyarmor's real CRUISER flat armor bonus is +400 (see
        # adapters/vanilla/__init__.py's DEFENSE_HULLMOD_EFFECTS); paired
        # with a fixture OP cost of 4, gain/OP = 100.0, exactly the
        # baseline_0.2 survivability_reference, so the mapped score is
        # exactly 100.0 -- same "hits the reference exactly" construction
        # the civilian_efficiency test above uses.
        hull = Hull("cruiser_h", "Cruiser Hull", "core", Path("h"), ordnance_points=20, hull_size="CRUISER",
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},), raw={"armor rating": 1000.0})
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        armor_mod = Hullmod("heavyarmor", "Heavy Armor", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 4})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[armor_mod]))
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="cruiser_h", weapons_by_mount={"A": "w"}, hullmods=("heavyarmor",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.2")
        self.assertIn("survivability", assessment.components)
        self.assertEqual(100.0, assessment.components["survivability"])  # gain 400 / OP 4 = 100.0, exactly the reference value
        self.assertTrue(any("Defense hullmod OP-efficiency" in line for line in assessment.explanation))

    def _flux_hullmod_fixture(self, hullmod_ids: tuple[str, ...] = ()):
        """DESTROYER hull/weapon pair sized so fluxdistributor's real +60
        DESTROYER bonus (adapters/vanilla/__init__.py's FLUX_HULLMOD_EFFECTS)
        moves dissipation_ratio from 0.5 (below the BALANCED 0.75 target,
        66.7 score) to 0.8 (at/above target, 100.0 score) -- a difference
        large enough to unambiguously prove hullmod-adjusted scoring is (or
        isn't) wired in, not just rounding noise.
        """
        hull = Hull("h_flux", "Flux Hull", "core", Path("h"), ordnance_points=60, hull_size="DESTROYER",
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},),
                    flux_dissipation=100.0, shield_upkeep=0.0)
        weapon = Weapon("w_flux", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC",
                         ordnance_points=10, range=500, flux_per_second=200.0)
        fluxdistributor = Hullmod("fluxdistributor", "Flux Distributor", "core", Path("m"), op_cost_by_hull_size={"DESTROYER": 8})
        safetyoverrides = Hullmod("safetyoverrides", "Safety Overrides", "core", Path("m"), op_cost_by_hull_size={"DESTROYER": 30})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[fluxdistributor, safetyoverrides]))
        variant = Variant("v_flux", "Variant", "core", Path("v"), hull_id="h_flux", weapons_by_mount={"A": "w_flux"}, hullmods=hullmod_ids)
        return registry, variant

    def test_baseline_0_7_flux_scoring_is_unaffected_by_a_hullmod_that_would_change_it_under_baseline_0_8(self) -> None:
        # Regression guarantee: baseline_0.7 must score fluxdistributor
        # identically to no hullmod at all -- the raw, unmodified hull stats
        # only, exactly as before this task's change.
        registry_none, variant_none = self._flux_hullmod_fixture(())
        registry_mod, variant_mod = self._flux_hullmod_fixture(("fluxdistributor",))
        without_hullmod = score_candidate(variant_none, registry_none, "LINE_ARTILLERY", "baseline_0.7", flux_mode="BALANCED")
        with_hullmod = score_candidate(variant_mod, registry_mod, "LINE_ARTILLERY", "baseline_0.7", flux_mode="BALANCED")
        self.assertEqual(66.7, without_hullmod.components["flux_sustainability"])
        self.assertEqual(66.7, with_hullmod.components["flux_sustainability"])
        self.assertEqual(without_hullmod.final_score, with_hullmod.final_score)
        self.assertFalse(any("hullmod-adjusted" in line for line in with_hullmod.explanation))

    def test_baseline_0_8_scores_fluxdistributor_adjusted_flux_dissipation(self) -> None:
        registry, variant = self._flux_hullmod_fixture(("fluxdistributor",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.8", flux_mode="BALANCED")
        # base 100 + DESTROYER's documented +60 = 160; ratio 160/200 = 0.8 >= 0.75 target -> saturates at 100.0.
        self.assertEqual(100.0, assessment.components["flux_sustainability"])
        self.assertTrue(any("flux_dissipation hullmod-adjusted for scoring: 100.00 -> 160.00 via fluxdistributor" in line for line in assessment.explanation))

    def test_baseline_0_8_without_the_hullmod_still_scores_the_raw_base_value(self) -> None:
        registry, variant = self._flux_hullmod_fixture(())
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.8", flux_mode="BALANCED")
        self.assertEqual(66.7, assessment.components["flux_sustainability"])
        self.assertFalse(any("hullmod-adjusted" in line for line in assessment.explanation))

    def test_baseline_0_8_stacking_falls_back_to_the_raw_base_value_with_an_explained_ambiguity(self) -> None:
        # fluxdistributor (flat-add) and safetyoverrides (multiply) both
        # target flux_dissipation; analysis/flux_stats.py's
        # compute_derived_flux_stats refuses to fabricate a combined value
        # for that collision, so scoring must fall back to the raw base
        # (documented decision (a)) rather than guess between 160.0 and
        # 200.0 -- never a silently-invented number in between.
        registry, variant = self._flux_hullmod_fixture(("fluxdistributor", "safetyoverrides"))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.8", flux_mode="BALANCED")
        self.assertEqual(66.7, assessment.components["flux_sustainability"])  # same as the raw-base 100.0 case, not 160.0 or 200.0
        self.assertTrue(any(
            "flux_dissipation hullmod stacking is unrepresentable, using unmodified base value" in line
            for line in assessment.explanation
        ))

    def _combat_hullmod_fixture(self, hullmod_ids: tuple[str, ...] = ()):
        """CRUISER hull with two ENERGY-mount weapons sized so targetingunit's
        real +40% CRUISER range bonus (adapters/vanilla/__init__.py's
        COMBAT_HULLMOD_EFFECTS) moves range_coherence's spread from 300
        (500 to 800 raw -- above range_mismatch_moderate's 250 but within
        range_mismatch_severe's 400, scoring 55.0) to 420 (700 to 1120
        boosted -- past range_mismatch_severe, scoring 25.0), a difference
        large enough to unambiguously prove hullmod-adjusted scoring is (or
        isn't) wired in, not just rounding noise.
        """
        hull = Hull("h_combat", "Combat Hull", "core", Path("h"), ordnance_points=60, hull_size="CRUISER",
                    weapon_mounts=(
                        {"id": "A", "type": "ENERGY", "size": "SMALL"},
                        {"id": "B", "type": "ENERGY", "size": "SMALL"},
                    ))
        w1 = Weapon("w1_combat", "Weapon 1", "core", Path("w"), size="SMALL", mount_type="ENERGY", ordnance_points=5, range=500.0)
        w2 = Weapon("w2_combat", "Weapon 2", "core", Path("w"), size="SMALL", mount_type="ENERGY", ordnance_points=5, range=800.0)
        targetingunit = Hullmod("targetingunit", "Integrated Targeting Unit", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 15})
        dedicated_targeting_core = Hullmod("dedicated_targeting_core", "Dedicated Targeting Core", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 15})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[w1, w2], hullmods=[targetingunit, dedicated_targeting_core]))
        variant = Variant("v_combat", "Variant", "core", Path("v"), hull_id="h_combat", weapons_by_mount={"A": "w1_combat", "B": "w2_combat"}, hullmods=hullmod_ids)
        return registry, variant

    def _combat_hullmod_role_match_fixture(self, hullmod_ids: tuple[str, ...] = ()):
        """Single-ENERGY-mount CRUISER hull sized so targetingunit's real
        +40% CRUISER range bonus moves the weapon's range across
        artillery_min_range (900): raw 750 fails role_match (70.0), boosted
        750 * 1.4 = 1050 passes it (100.0).
        """
        hull = Hull("h_role", "Role Hull", "core", Path("h"), ordnance_points=20, hull_size="CRUISER",
                    weapon_mounts=({"id": "A", "type": "ENERGY", "size": "SMALL"},))
        weapon = Weapon("w_role", "Weapon", "core", Path("w"), size="SMALL", mount_type="ENERGY", ordnance_points=5, range=750.0)
        targetingunit = Hullmod("targetingunit", "Integrated Targeting Unit", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 15})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[targetingunit]))
        variant = Variant("v_role", "Variant", "core", Path("v"), hull_id="h_role", weapons_by_mount={"A": "w_role"}, hullmods=hullmod_ids)
        return registry, variant

    def test_baseline_0_8_range_scoring_is_unaffected_by_a_hullmod_that_would_change_it_under_baseline_0_9(self) -> None:
        # Regression guarantee: baseline_0.8 (and, by the same construction,
        # baseline_0.7) must score targetingunit identically to no hullmod at
        # all -- the raw, unmodified weapon ranges only, exactly as before
        # this task's change.
        registry_none, variant_none = self._combat_hullmod_fixture(())
        registry_mod, variant_mod = self._combat_hullmod_fixture(("targetingunit",))
        without_hullmod = score_candidate(variant_none, registry_none, "LINE_ARTILLERY", "baseline_0.8")
        with_hullmod = score_candidate(variant_mod, registry_mod, "LINE_ARTILLERY", "baseline_0.8")
        self.assertEqual(55.0, without_hullmod.components["range_coherence"])
        self.assertEqual(55.0, with_hullmod.components["range_coherence"])
        self.assertEqual(without_hullmod.final_score, with_hullmod.final_score)
        self.assertFalse(any("hullmod-adjusted" in line for line in with_hullmod.explanation))

    def test_baseline_0_7_range_scoring_is_also_unaffected(self) -> None:
        registry_mod, variant_mod = self._combat_hullmod_fixture(("targetingunit",))
        with_hullmod = score_candidate(variant_mod, registry_mod, "LINE_ARTILLERY", "baseline_0.7")
        self.assertEqual(55.0, with_hullmod.components["range_coherence"])
        self.assertFalse(any("hullmod-adjusted" in line for line in with_hullmod.explanation))

    def test_baseline_0_9_scores_targetingunit_adjusted_range_coherence(self) -> None:
        registry, variant = self._combat_hullmod_fixture(("targetingunit",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.9")
        # 500 * 1.4 = 700, 800 * 1.4 = 1120 (CRUISER's documented +40%); spread 420 > range_mismatch_severe (400) -> 25.0.
        self.assertEqual(25.0, assessment.components["range_coherence"])
        self.assertTrue(any("w1_combat range hullmod-adjusted for scoring: 500 -> 700." in line for line in assessment.explanation))
        self.assertTrue(any("w2_combat range hullmod-adjusted for scoring: 800 -> 1120." in line for line in assessment.explanation))

    def test_baseline_0_9_without_the_hullmod_still_scores_the_raw_base_value(self) -> None:
        registry, variant = self._combat_hullmod_fixture(())
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.9")
        self.assertEqual(55.0, assessment.components["range_coherence"])
        self.assertFalse(any("hullmod-adjusted" in line for line in assessment.explanation))

    def test_baseline_0_9_stacking_falls_back_to_the_raw_base_value_with_an_explained_ambiguity(self) -> None:
        # targetingunit and dedicated_targeting_core both target the same
        # weapons' range; analysis/weapon_range_stats.py's
        # compute_derived_combat_stats refuses to fabricate a combined value
        # for that collision, so scoring must fall back to the raw base
        # (documented decision (a)) rather than guess a number between the
        # two verified bonuses.
        registry, variant = self._combat_hullmod_fixture(("targetingunit", "dedicated_targeting_core"))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.9")
        self.assertEqual(55.0, assessment.components["range_coherence"])  # same as the raw-base no-hullmod case, not 25.0
        self.assertTrue(any(
            "Weapon range hullmod stacking is unrepresentable, using unmodified base range" in line
            for line in assessment.explanation
        ))

    def test_baseline_0_8_role_match_scoring_is_unaffected_by_targetingunit(self) -> None:
        registry, variant = self._combat_hullmod_role_match_fixture(("targetingunit",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.8")
        self.assertEqual(70.0, assessment.components["role_match"])
        self.assertFalse(any("hullmod-adjusted" in line for line in assessment.explanation))

    def test_baseline_0_9_scores_targetingunit_adjusted_role_match(self) -> None:
        registry_raw, variant_raw = self._combat_hullmod_role_match_fixture(())
        registry_mod, variant_mod = self._combat_hullmod_role_match_fixture(("targetingunit",))
        raw = score_candidate(variant_raw, registry_raw, "LINE_ARTILLERY", "baseline_0.9")
        boosted = score_candidate(variant_mod, registry_mod, "LINE_ARTILLERY", "baseline_0.9")
        self.assertEqual(70.0, raw.components["role_match"])
        self.assertEqual(100.0, boosted.components["role_match"])
        self.assertTrue(any("w_role range hullmod-adjusted for scoring: 750 -> 1050." in line for line in boosted.explanation))

    def test_survivability_does_not_affect_baseline_0_1_scoring(self) -> None:
        hull = Hull("cruiser_h", "Cruiser Hull", "core", Path("h"), ordnance_points=20, hull_size="CRUISER",
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},), raw={"armor rating": 1000.0})
        weapon = Weapon("w", "Weapon", "core", Path("w"), size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        armor_mod = Hullmod("heavyarmor", "Heavy Armor", "core", Path("m"), op_cost_by_hull_size={"CRUISER": 4})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[armor_mod]))
        variant = Variant("v", "Variant", "core", Path("v"), hull_id="cruiser_h", weapons_by_mount={"A": "w"}, hullmods=("heavyarmor",))
        assessment = score_candidate(variant, registry, "LINE_ARTILLERY", "baseline_0.1")
        self.assertNotIn("survivability", assessment.components)


if __name__ == "__main__":
    unittest.main()
