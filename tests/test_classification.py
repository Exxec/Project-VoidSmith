from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.classification import classify_civilian_role, classify_fighter, classify_hull, classify_hullmod, classify_weapon
from starsector_variant_generator.core.models import FighterWing, Hull, Hullmod, Weapon


class ClassificationTests(unittest.TestCase):
    def test_hull_classification_uses_normalized_fighter_bays_not_raw_csv_text(self) -> None:
        hull = Hull("bad_bays", "Bad Bays", "fixture", Path("fixture.csv"), fighter_bays=None, raw={"fighter bays": "   "})
        self.assertEqual(0.0, classify_hull(hull).role_compatibility["CARRIER"])
    def test_weapon_tags_are_data_derived(self) -> None:
        weapon = Weapon("w", "Weapon", "core", Path("w"), mount_type="MISSILE", range=1000, damage_type="KINETIC", raw={"tags": "pd"})
        classified = classify_weapon(weapon)
        self.assertEqual("LONG", classified.range_band)
        self.assertEqual(("ARTILLERY", "KINETIC_PRESSURE", "MISSILE_PRESSURE", "PD"), classified.role_tags)

    def test_hull_roles_are_nonexclusive(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), weapon_mounts=({"type": "MISSILE", "size": "LARGE"},), launch_bay_slots=("BAY",))
        classified = classify_hull(hull)
        self.assertEqual(1.0, classified.role_compatibility["CARRIER"])
        self.assertEqual(1.0, classified.role_compatibility["MISSILE_SUPPORT"])

    def test_fighter_and_hullmod_classifiers_only_expose_parsed_properties(self) -> None:
        fighter = FighterWing("wing", "Wing", "core", Path("w"), role="INTERCEPTOR")
        hullmod = Hullmod("mod", "Mod", "core", Path("m"), hidden=True, built_in_only=True, op_cost_by_hull_size={"FRIGATE": 5})
        self.assertEqual(("SOURCE_ROLE:INTERCEPTOR",), classify_fighter(fighter).role_tags)
        self.assertEqual(("BUILT_IN_ONLY", "HIDDEN", "OP_TABLE_PRESENT"), classify_hullmod(hullmod).property_tags)

    def test_civilian_role_exposes_documented_hints_only(self) -> None:
        freighter = Hull("f", "Freighter", "core", Path("h"), hull_hints=("CIVILIAN", "FREIGHTER"), cargo_capacity=350.0, fuel_capacity=80.0)
        classified = classify_civilian_role(freighter)
        self.assertEqual(("CIVILIAN", "FREIGHTER"), classified.role_tags)
        self.assertTrue(classified.is_civilian)
        self.assertEqual(350.0, classified.cargo_capacity)

    def test_civilian_role_filters_out_structural_markers(self) -> None:
        module_hull = Hull("m", "Module", "core", Path("h"), hull_hints=("MODULE", "UNBOARDABLE"))
        classified = classify_civilian_role(module_hull)
        self.assertEqual((), classified.role_tags)
        self.assertFalse(classified.is_civilian)

    def test_combat_hull_without_hints_is_not_asserted_civilian_or_combat(self) -> None:
        combat_hull = Hull("c", "Combat", "core", Path("h"), cargo_capacity=100.0)
        classified = classify_civilian_role(combat_hull)
        self.assertEqual((), classified.role_tags)
        self.assertFalse(classified.is_civilian)


if __name__ == "__main__":
    unittest.main()
