from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import FighterWing, Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.refit import fix_legality, improve_quality
from starsector_variant_generator.validation.legality import LegalityResult

SOURCE = Path("fixture")


class FixLegalityTests(unittest.TestCase):
    def test_an_already_legal_variant_is_returned_unchanged(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual((), result.changes)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertFalse(result.rebuild_recommended)
        self.assertIs(variant, result.refitted_variant)

    def test_mount_type_mismatch_is_fixed_by_replacing_with_a_compatible_weapon(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        wrong = Weapon("wrong", "Wrong", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5)
        right = Weapon("right", "Right", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=4)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "wrong"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[wrong, right], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual({"A": "right"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual(1, len(result.changes))
        self.assertEqual("WEAPON_REPLACED", result.changes[0].kind)

    def test_mount_type_mismatch_falls_back_to_removal_when_no_compatible_weapon_exists(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        wrong = Weapon("wrong", "Wrong", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "wrong"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[wrong], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual({}, result.refitted_variant.weapons_by_mount)
        self.assertEqual("WEAPON_REMOVED", result.changes[0].kind)

    def test_op_exceeded_removes_the_highest_op_unlocked_item_first(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "SMALL"}, {"id": "B", "type": "BALLISTIC", "size": "SMALL"},
        ))
        cheap = Weapon("cheap", "Cheap", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=4)
        pricey = Weapon("pricey", "Pricey", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=8)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "cheap", "B": "pricey"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[cheap, pricey], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual({"A": "cheap"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual("WEAPON_REMOVED", result.changes[0].kind)
        self.assertEqual("B", result.changes[0].target_id)

    def test_built_in_weapon_override_is_removed_not_replaced(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10,
                    weapon_mounts=({"id": "A", "type": "BUILT_IN", "size": "SMALL"},),
                    built_in_weapons={"A": "fixed_gun"})
        wrong = Weapon("wrong", "Wrong", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=3)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "wrong"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[wrong], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual({}, result.refitted_variant.weapons_by_mount)
        self.assertEqual("WEAPON_REMOVED", result.changes[0].kind)

    def test_logistics_hullmod_limit_removes_only_the_excess(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=30)
        mods = [Hullmod(f"log_{i}", f"Log{i}", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1}, raw={"uiTags": "Logistics"}) for i in range(3)]
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", hullmods=tuple(m.id for m in mods))
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=mods, variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual(2, len(result.refitted_variant.hullmods))
        self.assertEqual(1, len(result.changes))

    def test_fighter_bay_capacity_removes_only_the_excess(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=30, fighter_bays=1)
        wings = [FighterWing(f"wing_{i}", f"Wing{i}", "core", SOURCE, op_cost=2) for i in range(2)]
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", fighter_wings=tuple(w.id for w in wings))
        registry = Registry.from_scan(ScanResult(hulls=[hull], fighters=wings, variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual(1, len(result.refitted_variant.fighter_wings))

    def test_flux_maximums_are_clamped_not_zeroed(self) -> None:
        from starsector_variant_generator.core.models import ScanResult as SR
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=50)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", flux_vents=99)
        registry = Registry.from_scan(SR(hulls=[hull], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual(10, result.refitted_variant.flux_vents)

    def test_locked_mount_is_never_touched_even_if_illegal(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        wrong = Weapon("wrong", "Wrong", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "wrong"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[wrong], variants=[variant]))
        result = fix_legality(variant, registry, locked_mount_ids=frozenset({"A"}))
        self.assertEqual({"A": "wrong"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual((), result.changes)
        self.assertTrue(result.rebuild_recommended)
        self.assertTrue(result.unresolved_failures)

    def test_a_not_determinable_result_reports_its_uncertainties_as_unresolved(self) -> None:
        # A mount type with no documented compatibility rule (e.g. real
        # LAUNCH_BAY/DECORATIVE mounts) lands the assessment in
        # NOT_DETERMINABLE, not ILLEGAL -- the blocker lives in
        # .uncertainties, not .failures. Refusing to guess at it is
        # correct; unresolved_failures must still surface *why*.
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "UNDOCUMENTED_TYPE", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(LegalityResult.NOT_DETERMINABLE, result.final_legality.result)
        self.assertTrue(result.rebuild_recommended)
        self.assertTrue(any(f.code == "MOUNT_TYPE_COMPATIBILITY_UNKNOWN" for f in result.unresolved_failures))

    def test_adaptive_mode_prefers_the_best_matching_weapon_over_the_cheapest(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        original = Weapon("original", "Original", "core", SOURCE, size="SMALL", mount_type="ENERGY", range=700, damage_type="HIGH_EXPLOSIVE", ordnance_points=6)
        cheap_bad_match = Weapon("cheap_bad_match", "CheapBadMatch", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", range=100, damage_type="KINETIC", ordnance_points=1)
        pricier_good_match = Weapon("pricier_good_match", "PricierGoodMatch", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", range=700, damage_type="HIGH_EXPLOSIVE", ordnance_points=6)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "original"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[original, cheap_bad_match, pricier_good_match], variants=[variant]))
        cheapest_result = fix_legality(variant, registry)
        self.assertEqual({"A": "cheap_bad_match"}, cheapest_result.refitted_variant.weapons_by_mount)
        adaptive_result = fix_legality(variant, registry, substitution_mode="adaptive")
        self.assertEqual({"A": "pricier_good_match"}, adaptive_result.refitted_variant.weapons_by_mount)
        self.assertEqual(LegalityResult.LEGAL, adaptive_result.final_legality.result)

    def test_exact_mode_never_substitutes_even_when_a_compatible_weapon_exists(self) -> None:
        # EQUIPMENT_ACCESS_AND_AUTOFIT.md section 9's EXACT: "Reproduce
        # specified IDs exactly. No substitution. Missing items are
        # reported." Unlike every other mode, this must remove the
        # incompatible weapon even though `right` is a perfectly compatible,
        # available replacement -- EXACT never looks for one.
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        wrong = Weapon("wrong", "Wrong", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5)
        right = Weapon("right", "Right", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=4)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "wrong"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[wrong, right], variants=[variant]))
        result = fix_legality(variant, registry, substitution_mode="exact")
        self.assertEqual(LegalityResult.LEGAL, result.final_legality.result)
        self.assertEqual({}, result.refitted_variant.weapons_by_mount)
        self.assertEqual("WEAPON_REMOVED", result.changes[0].kind)

    def test_starsector_style_mode_prefers_the_closest_category_match_over_adaptive_and_cheapest(self) -> None:
        # Three modes, three different real answers from the same fixture:
        # - "cheapest" picks the lowest-OP weapon regardless of match quality.
        # - "adaptive" picks the weapon with the best full weighted score,
        #   which favors the OP-efficiency component's bias toward
        #   cheaper-or-equal OP among otherwise-tied role/range/damage matches.
        # - "starsector_style" keeps the original's category/group tags
        #   (role_tags + range_band) as a hard filter, then breaks ties by
        #   the closest ordnance-point cost to the original -- not the
        #   cheapest, and not ADAPTIVE's weighted blend.
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        original = Weapon("original", "Original", "core", SOURCE, size="SMALL", mount_type="ENERGY", range=700, damage_type="HIGH_EXPLOSIVE", ordnance_points=6)
        cheap_bad_match = Weapon("cheap_bad_match", "CheapBadMatch", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", range=100, damage_type="KINETIC", ordnance_points=1)
        far_cheap_good_match = Weapon("far_cheap_good_match", "FarCheapGoodMatch", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", range=700, damage_type="HIGH_EXPLOSIVE", ordnance_points=2)
        close_pricier_good_match = Weapon("close_pricier_good_match", "ClosePricierGoodMatch", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", range=700, damage_type="HIGH_EXPLOSIVE", ordnance_points=7)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "original"})
        registry = Registry.from_scan(ScanResult(
            hulls=[hull], weapons=[original, cheap_bad_match, far_cheap_good_match, close_pricier_good_match], variants=[variant],
        ))
        cheapest_result = fix_legality(variant, registry)
        self.assertEqual({"A": "cheap_bad_match"}, cheapest_result.refitted_variant.weapons_by_mount)
        adaptive_result = fix_legality(variant, registry, substitution_mode="adaptive")
        self.assertEqual({"A": "far_cheap_good_match"}, adaptive_result.refitted_variant.weapons_by_mount)
        starsector_style_result = fix_legality(variant, registry, substitution_mode="starsector_style")
        self.assertEqual({"A": "close_pricier_good_match"}, starsector_style_result.refitted_variant.weapons_by_mount)
        self.assertEqual(LegalityResult.LEGAL, starsector_style_result.final_legality.result)

    def test_total_change_cost_sums_individual_change_costs(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        wrong = Weapon("wrong", "Wrong", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=5)
        right = Weapon("right", "Right", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=4)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "wrong"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[wrong, right], variants=[variant]))
        result = fix_legality(variant, registry)
        self.assertEqual(1.0, result.total_change_cost)  # baseline_0.2 refit_cost_weapon_change


class ImproveQualityTests(unittest.TestCase):
    def test_reduce_flux_prefers_the_lower_flux_compatible_weapon_without_regressing_role(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20, flux_dissipation=100.0, shield_upkeep=0.0,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        hot = Weapon("hot", "Hot", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500, flux_per_second=200.0)
        cool = Weapon("cool", "Cool", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500, flux_per_second=50.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "hot"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[hot, cool], variants=[variant]))
        result = improve_quality(variant, registry, "REDUCE_FLUX", "LINE_BRAWLER")
        self.assertEqual({"A": "cool"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual(1, len(result.changes))
        self.assertEqual("WEAPON_REPLACED", result.changes[0].kind)
        self.assertAlmostEqual(66.7, result.before_score, places=1)
        self.assertEqual(100.0, result.after_score)
        self.assertFalse(result.rebuild_recommended)

    def test_improve_role_match_prefers_the_in_range_weapon_for_an_artillery_profile(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        short = Weapon("short", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "short"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[short, long_ranged], variants=[variant]))
        result = improve_quality(variant, registry, "IMPROVE_ROLE_MATCH", "LINE_ARTILLERY")
        self.assertEqual({"A": "long_ranged"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual(70.0, result.before_score)
        self.assertEqual(100.0, result.after_score)

    def test_improve_role_match_can_complete_a_two_weapon_brawler_refit(self) -> None:
        """A coordinated search must cross the 70/100 metric plateau.

        Neither replacement changes role_match by itself because the other
        long-ranged weapon remains mounted.  Both legal swaps are required
        before the public all-weapons brawler condition becomes true.
        """
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20, weapon_mounts=(
            {"id": "A", "type": "BALLISTIC", "size": "SMALL"},
            {"id": "B", "type": "BALLISTIC", "size": "SMALL"},
        ))
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        short_ranged = Weapon("short_ranged", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "long_ranged", "B": "long_ranged"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[long_ranged, short_ranged], variants=[variant]))
        result = improve_quality(variant, registry, "IMPROVE_ROLE_MATCH", "LINE_BRAWLER")
        self.assertEqual({"A": "short_ranged", "B": "short_ranged"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual(2, len(result.changes))
        self.assertEqual(70.0, result.before_score)
        self.assertEqual(100.0, result.after_score)
        self.assertFalse(result.rebuild_recommended)

    def test_improve_logistics_adds_a_verified_cargo_hullmod_to_a_civilian_hull(self) -> None:
        hull = Hull("cargo_hull", "CargoHull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=20, cargo_capacity=100.0,
                    hull_hints=("CIVILIAN",), weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        token_weapon = Weapon("token", "Token", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=1, range=300)
        cargo_mod = Hullmod("expanded_cargo_holds", "ExpandedCargoHolds", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        variant = Variant("v", "V", "core", SOURCE, hull_id="cargo_hull", weapons_by_mount={"A": "token"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[token_weapon], hullmods=[cargo_mod], variants=[variant]))
        result = improve_quality(variant, registry, "IMPROVE_LOGISTICS", "LINE_BRAWLER")
        self.assertEqual(("expanded_cargo_holds",), result.refitted_variant.hullmods)
        self.assertEqual(1, len(result.changes))
        self.assertEqual("HULLMOD_ADDED", result.changes[0].kind)
        self.assertEqual(0.0, result.before_score)
        self.assertEqual(100.0, result.after_score)

    def test_improve_logistics_is_not_applicable_to_a_non_civilian_hull(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("w", "Weapon", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=300)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        result = improve_quality(variant, registry, "IMPROVE_LOGISTICS", "LINE_BRAWLER")
        self.assertEqual((), result.changes)
        self.assertIsNotNone(result.note)
        self.assertIs(variant, result.refitted_variant)

    def test_balanced_improvement_adds_only_a_verified_applicable_defense_hullmod(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=20,
                    raw={"armor rating": 300}, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        # The short weapon gives LINE_ARTILLERY a documented 70 role-match
        # starting component; a verified defense contribution improves the
        # existing overall score without modifying the locked loadout.
        weapon = Weapon("short", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        defense = Hullmod("heavyarmor", "Heavy Armor", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        unknown = Hullmod("unknown_defense", "Unknown", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "short"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[defense, unknown], variants=[variant]))
        result = improve_quality(variant, registry, "BALANCED_IMPROVEMENT", "LINE_ARTILLERY", locked_mount_ids=frozenset({"A"}))
        self.assertEqual(("heavyarmor",), result.refitted_variant.hullmods)
        self.assertEqual("HULLMOD_ADDED", result.changes[0].kind)
        self.assertGreater(result.after_score or 0.0, result.before_score or 0.0)

    def test_balanced_improvement_does_not_propose_a_defense_effect_without_its_base_stat(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=20,
                    weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("short", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        defense = Hullmod("heavyarmor", "Heavy Armor", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "short"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[defense], variants=[variant]))
        result = improve_quality(variant, registry, "BALANCED_IMPROVEMENT", "LINE_ARTILLERY", locked_mount_ids=frozenset({"A"}))
        self.assertEqual((), result.changes)

    def test_locked_mount_is_never_touched_during_quality_search(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=20, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        short = Weapon("short", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        long_ranged = Weapon("long_ranged", "Long", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=1000)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "short"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[short, long_ranged], variants=[variant]))
        result = improve_quality(variant, registry, "IMPROVE_ROLE_MATCH", "LINE_ARTILLERY", locked_mount_ids=frozenset({"A"}))
        self.assertEqual({"A": "short"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual((), result.changes)

    def test_a_change_that_would_make_the_variant_illegal_is_never_applied(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=5, weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        short = Weapon("short", "Short", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5, range=500)
        # Scores better for IMPROVE_ROLE_MATCH but exceeds the hull's OP budget.
        over_budget_long = Weapon("over_budget_long", "OverBudget", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=6, range=1000)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "short"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[short, over_budget_long], variants=[variant]))
        result = improve_quality(variant, registry, "IMPROVE_ROLE_MATCH", "LINE_ARTILLERY")
        self.assertEqual({"A": "short"}, result.refitted_variant.weapons_by_mount)
        self.assertEqual((), result.changes)

    def test_unimplemented_modes_raise_a_clear_error(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, ordnance_points=10)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        registry = Registry.from_scan(ScanResult(hulls=[hull], variants=[variant]))
        with self.assertRaises(ValueError):
            improve_quality(variant, registry, "IMPROVE_AI_FIT", "LINE_BRAWLER")
        with self.assertRaises(ValueError):
            improve_quality(variant, registry, "FIX_LEGALITY", "LINE_BRAWLER")


if __name__ == "__main__":
    unittest.main()
