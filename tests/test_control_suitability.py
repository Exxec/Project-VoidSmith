from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.control_suitability import compute_static_control_suitability
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry


SOURCE = Path("fixture")


def registry_with(*, hulls: tuple[Hull, ...] = (), weapons: tuple[Weapon, ...] = (), hullmods: tuple[Hullmod, ...] = ()) -> Registry:
    return Registry.from_scan(ScanResult(hulls=list(hulls), weapons=list(weapons), hullmods=list(hullmods)))


class RangeCoherenceTests(unittest.TestCase):
    def test_spread_and_mean_computed_from_real_weapon_ranges(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER")
        w1 = Weapon("w1", "W1", "core", SOURCE, mount_type="BALLISTIC", range=500.0)
        w2 = Weapon("w2", "W2", "core", SOURCE, mount_type="ENERGY", range=800.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w1", "B": "w2"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(w1, w2)))
        self.assertIsNotNone(result.range_coherence)
        self.assertEqual((500.0, 800.0), result.range_coherence.weapon_ranges)
        self.assertEqual(300.0, result.range_coherence.range_spread)
        self.assertEqual(650.0, result.range_coherence.mean_range)
        self.assertEqual(EvidenceClass.DIRECT_DATA, result.range_coherence.evidence_class)

    def test_none_when_no_equipped_weapon_has_a_known_range(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        w1 = Weapon("w1", "W1", "core", SOURCE, mount_type="BALLISTIC", range=None)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w1"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(w1,)))
        self.assertIsNone(result.range_coherence)

    def test_none_when_no_weapons_equipped_at_all(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNone(result.range_coherence)


class FluxStabilityTests(unittest.TestCase):
    def test_dissipation_ratio_against_sustained_load(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", flux_dissipation=200.0, shield_upkeep=20.0)
        weapon = Weapon("w", "W", "core", SOURCE, mount_type="ENERGY", flux_per_second=80.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(weapon,)))
        self.assertIsNotNone(result.flux_stability)
        self.assertEqual(200.0, result.flux_stability.flux_dissipation)
        self.assertEqual(100.0, result.flux_stability.sustained_flux_load)
        self.assertEqual(2.0, result.flux_stability.dissipation_ratio)
        self.assertEqual(EvidenceClass.DIRECT_DATA, result.flux_stability.evidence_class)

    def test_none_when_hull_flux_dissipation_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=None)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNone(result.flux_stability)

    def test_none_when_any_equipped_weapon_flux_is_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=200.0)
        w1 = Weapon("w1", "W1", "core", SOURCE, mount_type="ENERGY", flux_per_second=50.0)
        w2 = Weapon("w2", "W2", "core", SOURCE, mount_type="BALLISTIC", flux_per_second=None)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w1", "B": "w2"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(w1, w2)))
        self.assertIsNone(result.flux_stability)

    def test_ratio_is_none_when_there_is_no_sustained_load(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=200.0, shield_upkeep=None)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNotNone(result.flux_stability)
        self.assertEqual(0.0, result.flux_stability.sustained_flux_load)
        self.assertIsNone(result.flux_stability.dissipation_ratio)


class BurstDependenceTests(unittest.TestCase):
    def test_shot_interval_computed_from_real_flux_fields(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER")
        weapon = Weapon("w", "W", "core", SOURCE, mount_type="BALLISTIC", flux_per_shot=40.0, flux_per_second=20.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(weapon,)))
        self.assertIsNotNone(result.burst_dependence)
        self.assertEqual((("A", 2.0),), result.burst_dependence.per_mount_shot_intervals)
        self.assertEqual(2.0, result.burst_dependence.mean_shot_interval)
        self.assertEqual((), result.burst_dependence.excluded_weapon_ids)
        self.assertEqual(EvidenceClass.DIRECT_DATA, result.burst_dependence.evidence_class)

    def test_beam_style_weapon_with_no_per_shot_cost_is_excluded_not_fabricated(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER")
        burst = Weapon("burst", "Burst", "core", SOURCE, mount_type="BALLISTIC", flux_per_shot=40.0, flux_per_second=20.0)
        beam = Weapon("beam", "Beam", "core", SOURCE, mount_type="ENERGY", flux_per_shot=None, flux_per_second=30.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "burst", "B": "beam"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(burst, beam)))
        self.assertIsNotNone(result.burst_dependence)
        self.assertEqual((("A", 2.0),), result.burst_dependence.per_mount_shot_intervals)
        self.assertEqual(("beam",), result.burst_dependence.excluded_weapon_ids)

    def test_none_when_no_equipped_weapon_has_a_discrete_per_shot_cost(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        beam = Weapon("beam", "Beam", "core", SOURCE, mount_type="ENERGY", flux_per_shot=None, flux_per_second=30.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "beam"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(beam,)))
        self.assertIsNone(result.burst_dependence)


class AmmoDependenceTests(unittest.TestCase):
    def test_missile_op_fraction_from_real_mount_type_and_ordnance_points(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CRUISER")
        missile = Weapon("m", "Missile", "core", SOURCE, mount_type="MISSILE", ordnance_points=10)
        ballistic = Weapon("b", "Ballistic", "core", SOURCE, mount_type="BALLISTIC", ordnance_points=10)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "m", "B": "b"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(missile, ballistic)))
        self.assertIsNotNone(result.ammo_dependence)
        self.assertEqual(1, result.ammo_dependence.missile_mount_count)
        self.assertEqual(2, result.ammo_dependence.total_mount_count)
        self.assertEqual(0.5, result.ammo_dependence.missile_op_fraction)
        self.assertEqual(EvidenceClass.DIRECT_DATA, result.ammo_dependence.evidence_class)

    def test_none_when_no_weapons_equipped(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNone(result.ammo_dependence)

    def test_fraction_is_none_but_counts_still_populate_when_op_is_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        missile = Weapon("m", "Missile", "core", SOURCE, mount_type="MISSILE", ordnance_points=None)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "m"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(missile,)))
        self.assertIsNotNone(result.ammo_dependence)
        self.assertEqual(1, result.ammo_dependence.missile_mount_count)
        self.assertEqual(1, result.ammo_dependence.total_mount_count)
        self.assertIsNone(result.ammo_dependence.missile_op_fraction)


class MobilityVsEngagementRangeTests(unittest.TestCase):
    def test_reports_effective_speed_and_real_weapon_ranges_unfused(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={"max speed": "60"})
        weapon = Weapon("w", "W", "core", SOURCE, mount_type="BALLISTIC", range=600.0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"}, hullmods=("unstable_injector",))
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(weapon,)))
        self.assertIsNotNone(result.mobility_vs_engagement_range)
        self.assertEqual(80.0, result.mobility_vs_engagement_range.effective_max_speed)
        self.assertEqual(600.0, result.mobility_vs_engagement_range.mean_weapon_range)
        self.assertEqual(600.0, result.mobility_vs_engagement_range.max_weapon_range)
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, result.mobility_vs_engagement_range.evidence_class)

    def test_falls_back_to_base_speed_when_effective_value_unavailable(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"max speed": "60"})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNotNone(result.mobility_vs_engagement_range)
        self.assertEqual(60.0, result.mobility_vs_engagement_range.effective_max_speed)
        self.assertIsNone(result.mobility_vs_engagement_range.mean_weapon_range)

    def test_none_when_neither_speed_nor_range_is_known(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNone(result.mobility_vs_engagement_range)


class SystemComplexityTests(unittest.TestCase):
    def test_reads_real_ship_system_id_from_ship_data(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={"ship_data": {"shipSystemId": "flare_launcher"}})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNotNone(result.system_complexity)
        self.assertTrue(result.system_complexity.has_ship_system)
        self.assertEqual("flare_launcher", result.system_complexity.ship_system_id)
        self.assertEqual(EvidenceClass.DIRECT_DATA, result.system_complexity.evidence_class)

    def test_no_system_is_real_negative_evidence_not_absence(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={"ship_data": {}})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNotNone(result.system_complexity)
        self.assertFalse(result.system_complexity.has_ship_system)
        self.assertIsNone(result.system_complexity.ship_system_id)

    def test_skin_override_takes_precedence_over_base_hull(self) -> None:
        base = Hull("base", "Base", "core", SOURCE, hull_size="DESTROYER", raw={"ship_data": {"shipSystemId": "burn_drive"}})
        skin = Hull("skin", "Skin", "core", SOURCE, hull_size="DESTROYER", raw={"skin_data": {"systemId": "flare_launcher"}, "base_hull_id": "base"})
        variant = Variant("v", "V", "core", SOURCE, hull_id="skin")
        result = compute_static_control_suitability(variant, skin, registry_with(hulls=(base,)))
        self.assertEqual("flare_launcher", result.system_complexity.ship_system_id)

    def test_skin_without_its_own_override_falls_back_one_level_to_base_hull(self) -> None:
        base = Hull("base", "Base", "core", SOURCE, hull_size="DESTROYER", raw={"ship_data": {"shipSystemId": "burn_drive"}})
        skin = Hull("skin", "Skin", "core", SOURCE, hull_size="DESTROYER", raw={"skin_data": {}, "base_hull_id": "base"})
        variant = Variant("v", "V", "core", SOURCE, hull_id="skin")
        result = compute_static_control_suitability(variant, skin, registry_with(hulls=(base,)))
        self.assertEqual("burn_drive", result.system_complexity.ship_system_id)

    def test_none_when_no_ship_data_is_available_at_all(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNone(result.system_complexity)


class WeaponGroupComplexityTests(unittest.TestCase):
    def test_counts_mounts_mount_types_and_declared_weapon_groups(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CRUISER")
        w1 = Weapon("w1", "W1", "core", SOURCE, mount_type="BALLISTIC")
        w2 = Weapon("w2", "W2", "core", SOURCE, mount_type="ENERGY")
        w3 = Weapon("w3", "W3", "core", SOURCE, mount_type="BALLISTIC")
        variant = Variant(
            "v", "V", "core", SOURCE, hull_id="h",
            weapons_by_mount={"A": "w1", "B": "w2", "C": "w3"},
            raw={"weaponGroups": [{"weapons": {"A": "w1"}}, {"weapons": {"B": "w2", "C": "w3"}}]},
        )
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(w1, w2, w3)))
        self.assertIsNotNone(result.weapon_group_complexity)
        self.assertEqual(3, result.weapon_group_complexity.equipped_mount_count)
        self.assertEqual(2, result.weapon_group_complexity.distinct_mount_type_count)
        self.assertEqual(2, result.weapon_group_complexity.weapon_group_count)
        self.assertEqual(EvidenceClass.DIRECT_DATA, result.weapon_group_complexity.evidence_class)

    def test_group_count_is_none_without_raw_weapon_groups_but_counts_still_populate(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        weapon = Weapon("w", "W", "core", SOURCE, mount_type="BALLISTIC")
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", weapons_by_mount={"A": "w"})
        result = compute_static_control_suitability(variant, hull, registry_with(weapons=(weapon,)))
        self.assertIsNotNone(result.weapon_group_complexity)
        self.assertEqual(1, result.weapon_group_complexity.equipped_mount_count)
        self.assertIsNone(result.weapon_group_complexity.weapon_group_count)


class SurvivabilityPostureTests(unittest.TestCase):
    def test_reuses_verified_defense_hullmod_effects(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300", "hitpoints": "4000"})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h", hullmods=("reinforcedhull",))
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNotNone(result.survivability_posture)
        self.assertEqual(300.0, result.survivability_posture.armor_rating_base)
        self.assertEqual(4000.0, result.survivability_posture.hull_hp_base)
        self.assertEqual(5600.0, result.survivability_posture.effective_hull_hp)
        self.assertEqual(("reinforcedhull",), result.survivability_posture.applied_defense_hullmod_ids)
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, result.survivability_posture.evidence_class)

    def test_none_when_base_armor_and_hp_are_both_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={})
        variant = Variant("v", "V", "core", SOURCE, hull_id="h")
        result = compute_static_control_suitability(variant, hull, registry_with())
        self.assertIsNone(result.survivability_posture)


class ModuleBoundaryTests(unittest.TestCase):
    def test_module_never_imports_or_references_legality(self) -> None:
        """Hard framing/architecture boundary: this is a static structural
        signal set, never a legality determination. Explicit guard mirroring
        test_calibration_activation.py's own heuristic-registry import guard.
        """
        import starsector_variant_generator.analysis.control_suitability as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("validation.legality", source)
        self.assertNotIn("validation import legality", source)
        self.assertNotIn("validate_variant", source)
        self.assertNotIn("LegalityResult", source)

    def test_field_name_is_explicitly_labeled_static_control_suitability(self) -> None:
        from starsector_variant_generator.analysis.control_suitability import StaticControlSuitability

        self.assertEqual("StaticControlSuitability", StaticControlSuitability.__name__)
        self.assertIn("STATIC_CONTROL_SUITABILITY", StaticControlSuitability.__doc__ or "")
        module_doc = __import__(
            "starsector_variant_generator.analysis.control_suitability", fromlist=["__doc__"],
        ).__doc__ or ""
        self.assertIn("STATIC_CONTROL_SUITABILITY", module_doc)
        self.assertIn("NOT a combat outcome predictor", module_doc)


if __name__ == "__main__":
    unittest.main()
