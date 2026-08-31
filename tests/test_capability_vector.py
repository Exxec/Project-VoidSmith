from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.capability_vector import (
    CAPABILITY_DIMENSIONS,
    infer_hull_capability_vector,
)
from starsector_variant_generator.core.models import (
    Hull,
    Hullmod,
    ScanResult,
    Variant,
    Weapon,
)
from starsector_variant_generator.core.registry import Registry


class CapabilityVectorTests(unittest.TestCase):
    def test_vector_preserves_unknown_weapon_behavior_without_variants(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), raw={"armor rating": 900, "hitpoints": 7000, "max speed": 60})
        vector = infer_hull_capability_vector(hull, Registry.from_scan(ScanResult(hulls=[hull])))
        self.assertEqual(set(CAPABILITY_DIMENSIONS), set(vector.dimensions))
        self.assertEqual("UNKNOWN", vector.dimensions["KINETIC_PRESSURE"].availability)
        self.assertIsNone(vector.dimensions["KINETIC_PRESSURE"].score)
        self.assertEqual("AVAILABLE", vector.dimensions["ARMOR_TANKING"].availability)

    def test_variant_weapons_supply_descriptive_pressure_evidence(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), weapon_mounts=({"id": "A", "type": "BALLISTIC", "size": "SMALL"},))
        weapon = Weapon("kinetic", "Kinetic", "core", Path("fixture"), mount_type="BALLISTIC", size="SMALL", damage_type="KINETIC", raw={"tags": "pd"})
        variant = Variant("v", "Variant", "core", Path("fixture"), hull_id="h", weapons_by_mount={"A": "kinetic"})
        vector = infer_hull_capability_vector(hull, Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant])))
        self.assertEqual(1.0, vector.dimensions["KINETIC_PRESSURE"].score)
        self.assertEqual(1.0, vector.dimensions["PD_SCREENING"].score)

    def test_verified_variant_mobility_effect_enriches_mobility_evidence(self) -> None:
        hull = Hull("h", "Hull", "core", Path("fixture"), hull_size="FRIGATE", raw={"max speed": "60"})
        injector = Hullmod("unstable_injector", "Injector", "core", Path("fixture"), op_cost_by_hull_size={"FRIGATE": 5})
        variant = Variant("v", "Variant", "core", Path("fixture"), hull_id="h", hullmods=("unstable_injector",))
        vector = infer_hull_capability_vector(hull, Registry.from_scan(ScanResult(hulls=[hull], hullmods=[injector], variants=[variant])))
        self.assertAlmostEqual(85 / 120, vector.dimensions["MOBILITY"].score or 0.0, places=6)
        self.assertIn("adapter-backed", " ".join(vector.dimensions["MOBILITY"].supporting_evidence))


if __name__ == "__main__":
    unittest.main()
