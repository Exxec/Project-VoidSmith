from __future__ import annotations

import unittest
import unittest.mock
from pathlib import Path

from starsector_variant_generator.core.models import FighterWing, Hull, Hullmod, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.validation.legality import LegalityResult, validate_variant


SOURCE = Path("fixture")


def registry_for(variant: Variant, weapon: Weapon) -> Registry:
    hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=10,
                weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BALLISTIC"},))
    return Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))


class LegalityTests(unittest.TestCase):
    def test_legal_when_documented_mount_and_op_evidence_is_complete(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"})
        self.assertEqual(LegalityResult.LEGAL, validate_variant(variant, registry_for(variant, weapon)).result)

    def test_oversized_weapon_is_illegal_even_if_other_data_is_unknown(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="LARGE", mount_type=None, ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"})
        self.assertEqual(LegalityResult.ILLEGAL, validate_variant(variant, registry_for(variant, weapon)).result)

    def test_unknown_mount_semantics_are_not_scored_or_assumed_legal(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type=None, ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"})
        self.assertEqual(LegalityResult.NOT_DETERMINABLE, validate_variant(variant, registry_for(variant, weapon)).result)

    def test_hybrid_composite_synergy_and_universal_mounts_accept_their_documented_combinations(self) -> None:
        # Verified against real developer-authored vanilla variants, not
        # exact-string-match: a HYBRID mount takes BALLISTIC or ENERGY
        # weapons, not just weapons whose own mount_type is "HYBRID".
        hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=50, weapon_mounts=(
            {"id": "H", "size": "SMALL", "type": "HYBRID"},
            {"id": "C", "size": "SMALL", "type": "COMPOSITE"},
            {"id": "S", "size": "SMALL", "type": "SYNERGY"},
            {"id": "U", "size": "SMALL", "type": "UNIVERSAL"},
        ))
        ballistic = Weapon("ballistic_gun", "B", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=1)
        energy = Weapon("energy_gun", "E", "core", SOURCE, size="SMALL", mount_type="ENERGY", ordnance_points=1)
        missile = Weapon("missile_rack", "M", "core", SOURCE, size="SMALL", mount_type="MISSILE", ordnance_points=1)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[ballistic, energy, missile]))
        variant = Variant("v", "V", "core", SOURCE, hull_id="hull", weapons_by_mount={"H": "ballistic_gun", "C": "missile_rack", "S": "energy_gun", "U": "missile_rack"})
        assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.LEGAL, assessment.result)

    def test_hybrid_mount_still_rejects_an_incompatible_missile_weapon(self) -> None:
        hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=10,
                    weapon_mounts=({"id": "H", "size": "SMALL", "type": "HYBRID"},))
        missile = Weapon("missile_rack", "M", "core", SOURCE, size="SMALL", mount_type="MISSILE", ordnance_points=1)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[missile]))
        variant = Variant("v", "V", "core", SOURCE, hull_id="hull", weapons_by_mount={"H": "missile_rack"})
        assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("MOUNT_TYPE_MISMATCH", {finding.code for finding in assessment.failures})

    def test_documented_hullmod_op_is_included_in_hard_limit(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("mod",))
        registry = registry_for(variant, weapon)
        registry.hullmods = registry.hullmods.build([Hullmod("mod", "Mod", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 6})])
        self.assertEqual(LegalityResult.ILLEGAL, validate_variant(variant, registry).result)

    def test_missing_hullmod_and_fighter_references_are_illegal(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("missing_mod",), fighter_wings=("missing_wing",))
        assessment = validate_variant(variant, registry_for(variant, weapon))
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertEqual({"HULLMOD_NOT_FOUND", "FIGHTER_WING_NOT_FOUND"}, {finding.code for finding in assessment.failures})

    def test_built_in_weapon_mount_cannot_be_overridden(self) -> None:
        hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=10,
                    weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BUILT_IN"},),
                    built_in_weapons={"WS 1": "flak"}, raw={"ship_data": {}})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[
            Weapon("flak", "Flak", "core", SOURCE, size="SMALL", mount_type="BUILT_IN", ordnance_points=0),
            Weapon("gun2", "Gun", "core", SOURCE, size="SMALL", mount_type="BUILT_IN", ordnance_points=0),
        ]))
        matching = Variant("v1", "V1", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "flak"})
        self.assertEqual(LegalityResult.LEGAL, validate_variant(matching, registry).result)
        overridden = Variant("v2", "V2", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun2"})
        assessment = validate_variant(overridden, registry)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("BUILT_IN_WEAPON_OVERRIDDEN", {finding.code for finding in assessment.failures})

    def test_fighter_wing_count_cannot_exceed_documented_fighter_bays(self) -> None:
        # Capacity comes from hull.fighter_bays (the CSV "fighter bays"
        # column), not len(launch_bay_slots) -- see the comment on
        # Hull.fighter_bays in core/models.py for why the two can differ.
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=10,
                    weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BALLISTIC"},),
                    fighter_bays=1)
        wing = FighterWing("wing", "Wing", "core", SOURCE, op_cost=0)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], fighters=[wing]))
        within_capacity = Variant("v1", "V1", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, fighter_wings=("wing",))
        self.assertEqual(LegalityResult.LEGAL, validate_variant(within_capacity, registry).result)
        over_capacity = Variant("v2", "V2", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, fighter_wings=("wing", "wing"))
        assessment = validate_variant(over_capacity, registry)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("FIGHTER_BAY_CAPACITY_EXCEEDED", {finding.code for finding in assessment.failures})

    def test_fighter_wing_count_is_not_determinable_without_parsed_ship_data(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        wing = FighterWing("wing", "Wing", "core", SOURCE, op_cost=0)
        variant = Variant("v", "V", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, fighter_wings=("wing",))
        registry = registry_for(variant, weapon)
        registry.fighters = registry.fighters.build([wing])
        assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.NOT_DETERMINABLE, assessment.result)
        self.assertIn("FIGHTER_BAY_CAPACITY_UNKNOWN", {finding.code for finding in assessment.uncertainties})

    def test_hullmod_incompatibility_pairs_are_illegal_when_documented(self) -> None:
        from starsector_variant_generator.adapters import vanilla as vanilla_adapter
        from starsector_variant_generator.adapters.vanilla import HullmodIncompatibility

        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("mod_a", "mod_b"))
        registry = registry_for(variant, weapon)
        registry.hullmods = registry.hullmods.build([
            Hullmod("mod_a", "Mod A", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 0}),
            Hullmod("mod_b", "Mod B", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 0}),
        ])
        fixture_pairs = (HullmodIncompatibility("mod_a", "mod_b", "fixture citation"),)
        with unittest.mock.patch.object(vanilla_adapter, "INCOMPATIBLE_HULLMOD_PAIRS", fixture_pairs):
            assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("HULLMOD_INCOMPATIBLE", {finding.code for finding in assessment.failures})

    def test_documented_vent_and_capacitor_op_cost_is_included_in_the_hard_limit(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, flux_vents=5)
        assessment = validate_variant(variant, registry_for(variant, weapon))
        self.assertEqual(LegalityResult.LEGAL, assessment.result)
        self.assertIn("OP_WITHIN_LIMIT", {finding.code for finding in assessment.evidence})

        over_budget = Variant("v2", "V2", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, flux_vents=6)
        over_assessment = validate_variant(over_budget, registry_for(over_budget, weapon))
        self.assertEqual(LegalityResult.ILLEGAL, over_assessment.result)
        self.assertIn("OP_EXCEEDED", {finding.code for finding in over_assessment.failures})

    def test_vent_and_capacitor_counts_cannot_exceed_the_documented_hull_size_maximum(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=0)
        hull = Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", ordnance_points=99,
                    weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BALLISTIC"},))
        variant = Variant("v", "V", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, flux_vents=11)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("FLUX_VENTS_EXCEED_HULL_MAXIMUM", {finding.code for finding in assessment.failures})

    def test_vent_cap_op_is_not_determinable_for_a_mod_hull_without_a_documented_cost(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        hull = Hull("hull", "Hull", "fixture_mod", SOURCE, hull_size="FRIGATE", ordnance_points=10,
                    weapon_mounts=({"id": "WS 1", "size": "SMALL", "type": "BALLISTIC"},))
        variant = Variant("v", "V", "fixture_mod", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, flux_vents=2)
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant]))
        assessment = validate_variant(variant, registry)
        self.assertEqual(LegalityResult.NOT_DETERMINABLE, assessment.result)
        self.assertIn("VENT_CAP_OP_UNKNOWN", {finding.code for finding in assessment.uncertainties})

    def test_logistics_hullmod_count_cannot_exceed_the_documented_maximum(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        logistics_mod = lambda mod_id: Hullmod(mod_id, mod_id, "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 0}, raw={"uiTags": "Logistics, Requires Dock"})
        within_limit = Variant("v1", "V1", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("mod_a", "mod_b"))
        registry = registry_for(within_limit, weapon)
        registry.hullmods = registry.hullmods.build([logistics_mod("mod_a"), logistics_mod("mod_b")])
        self.assertEqual(LegalityResult.LEGAL, validate_variant(within_limit, registry).result)

        over_limit = Variant("v2", "V2", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("mod_a", "mod_b", "mod_c"))
        registry2 = registry_for(over_limit, weapon)
        registry2.hullmods = registry2.hullmods.build([logistics_mod("mod_a"), logistics_mod("mod_b"), logistics_mod("mod_c")])
        assessment = validate_variant(over_limit, registry2)
        self.assertEqual(LegalityResult.ILLEGAL, assessment.result)
        self.assertIn("LOGISTICS_HULLMOD_LIMIT_EXCEEDED", {finding.code for finding in assessment.failures})

    def test_untagged_hullmods_are_never_counted_as_logistics(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        plain_mod = lambda mod_id: Hullmod(mod_id, mod_id, "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 0})
        variant = Variant("v", "V", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("mod_a", "mod_b", "mod_c"))
        registry = registry_for(variant, weapon)
        registry.hullmods = registry.hullmods.build([plain_mod("mod_a"), plain_mod("mod_b"), plain_mod("mod_c")])
        self.assertEqual(LegalityResult.LEGAL, validate_variant(variant, registry).result)

    def test_empty_hullmod_incompatibility_table_asserts_nothing(self) -> None:
        weapon = Weapon("gun", "Gun", "core", SOURCE, size="SMALL", mount_type="BALLISTIC", ordnance_points=5)
        variant = Variant("variant", "Variant", "core", SOURCE, hull_id="hull", weapons_by_mount={"WS 1": "gun"}, hullmods=("mod_a", "mod_b"))
        registry = registry_for(variant, weapon)
        registry.hullmods = registry.hullmods.build([
            Hullmod("mod_a", "Mod A", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 0}),
            Hullmod("mod_b", "Mod B", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 0}),
        ])
        self.assertEqual(LegalityResult.LEGAL, validate_variant(variant, registry).result)


if __name__ == "__main__":
    unittest.main()
