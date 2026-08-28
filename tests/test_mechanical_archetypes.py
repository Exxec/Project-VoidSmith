from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.mechanical_archetypes import ARCHETYPES, infer_hull_feature_vector, infer_mechanical_archetypes
from starsector_variant_generator.core.models import Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class MechanicalArchetypeTests(unittest.TestCase):
    def test_all_requested_archetypes_are_present_with_evidence(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CRUISER", ordnance_points=120,
                    fighter_bays=2, cargo_capacity=700, fuel_capacity=800,
                    hull_hints=("CIVILIAN", "FREIGHTER", "COMBAT"),
                    weapon_mounts=({"type": "BALLISTIC", "size": "LARGE", "arc": 60}, {"type": "MISSILE", "size": "MEDIUM", "arc": 180}),
                    raw={"armor rating": "1200", "hitpoints": "12000", "max speed": "55", "shield type": "OMNI"})
        profile = infer_mechanical_archetypes(hull)
        self.assertEqual(ARCHETYPES, tuple(profile.compatibility_scores))
        self.assertEqual(set(ARCHETYPES), set(profile.evidence_by_archetype))
        self.assertGreater(profile.compatibility_scores["COMBAT_FREIGHTER"], 0.0)
        self.assertGreater(profile.compatibility_scores["BATTLECARRIER"], 0.0)

    def test_variants_supply_statistical_not_structural_evidence(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, weapon_mounts=(
            {"id": "M", "type": "MISSILE", "size": "MEDIUM"}, {"id": "S", "type": "BALLISTIC", "size": "SMALL"},
        ))
        missile = Weapon("m", "Missile", "core", SOURCE, mount_type="MISSILE", range=1200)
        pd = Weapon("pd", "PD", "core", SOURCE, mount_type="BALLISTIC", range=500, raw={"tags": "pd"})
        variant = Variant("v", "Variant", "core", SOURCE, hull_id="h", weapons_by_mount={"M": "m", "S": "pd"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[missile, pd], variants=[variant]))
        vector = infer_hull_feature_vector(hull, registry)
        self.assertEqual(1, vector.existing_variant_count)
        self.assertEqual(0.5, vector.variant_missile_mount_fraction)
        self.assertEqual(0.5, vector.variant_pd_weapon_fraction)
        self.assertEqual(0.5, vector.variant_long_range_weapon_fraction)
        profile = infer_mechanical_archetypes(hull, registry)
        self.assertIn("existing_variant_evidence", " ".join(profile.evidence_by_archetype["MISSILE_SUPPORT"]))

    def test_unknown_shield_and_system_are_preserved_not_guessed(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, raw={"systemId": "custom_scripted_system"})
        vector = infer_hull_feature_vector(hull)
        self.assertIsNone(vector.has_shield)
        self.assertEqual("custom_scripted_system", vector.ship_system_id)
        self.assertEqual((), vector.known_ship_system_categories)

    def test_inference_is_deterministic(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_hints=("CIVILIAN", "TANKER"), fuel_capacity=2000)
        self.assertEqual(infer_mechanical_archetypes(hull), infer_mechanical_archetypes(hull))


if __name__ == "__main__":
    unittest.main()
