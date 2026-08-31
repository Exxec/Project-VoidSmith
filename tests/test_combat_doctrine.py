from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.combat_doctrine import infer_combat_doctrine
from starsector_variant_generator.core.models import Hull, ScanResult, Variant, Weapon
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


class CombatDoctrineTests(unittest.TestCase):
    def test_profile_is_multivalued_and_uses_variant_weapon_evidence(self) -> None:
        hull = Hull(
            "anchor", "Anchor", "core", SOURCE, ordnance_points=150, flux_capacity=15000, flux_dissipation=1100,
            weapon_mounts=tuple({"type": "BALLISTIC", "size": "LARGE", "arc": 60} for _ in range(3)),
            raw={"armor rating": 1300, "hitpoints": 12000, "max speed": 45, "acceleration": 30, "max turn rate": 20},
        )
        weapon = Weapon("long", "Long", "core", SOURCE, mount_type="BALLISTIC", range=1400)
        variant = Variant("anchor_std", "Anchor", "core", SOURCE, hull_id="anchor", weapons_by_mount={"a": "long"})
        profile = infer_combat_doctrine(hull, Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], variants=[variant])))

        self.assertGreater(profile.battlefield_function.scores["LINE_ANCHOR"], 0.5)
        self.assertGreater(profile.battlefield_function.scores["FIRE_SUPPORT"], 0.3)
        self.assertGreater(profile.engagement_position.scores["FRONT_LINE"], 0.4)
        self.assertGreater(profile.tactical_style.scores["SUSTAINED_ASSAULT"], 0.4)
        self.assertIn("SUSTAINED", profile.tempo.scores)
        self.assertIn("FORMATION_DEPENDENT", profile.fleet_dependence.scores)
        self.assertTrue(profile.battlefield_function.evidence)

    def test_unknown_runtime_labels_are_not_emitted(self) -> None:
        profile = infer_combat_doctrine(Hull("h", "Hull", "core", SOURCE))
        self.assertNotIn("RAMMING", profile.tactical_style.scores)
        self.assertNotIn("RESERVE", profile.engagement_position.scores)
        self.assertNotIn("SYSTEM_DEPENDENT", profile.tempo.scores)
        self.assertNotIn("SWARM_DEPENDENT", profile.fleet_dependence.scores)


if __name__ == "__main__":
    unittest.main()
