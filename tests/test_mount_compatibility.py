from __future__ import annotations

import unittest

from starsector_variant_generator.core.mount_compatibility import (
    MOUNT_TYPE_COMPATIBILITY,
)


class MountCompatibilityTests(unittest.TestCase):
    def test_basic_mount_types_only_accept_their_own_weapon_type(self) -> None:
        for mount_type in ("BALLISTIC", "ENERGY", "MISSILE"):
            self.assertEqual({mount_type}, set(MOUNT_TYPE_COMPATIBILITY[mount_type]))

    def test_combination_mounts_accept_their_two_component_types_and_themselves(self) -> None:
        self.assertEqual({"BALLISTIC", "ENERGY", "HYBRID"}, set(MOUNT_TYPE_COMPATIBILITY["HYBRID"]))
        self.assertEqual({"BALLISTIC", "MISSILE", "COMPOSITE"}, set(MOUNT_TYPE_COMPATIBILITY["COMPOSITE"]))
        self.assertEqual({"ENERGY", "MISSILE", "SYNERGY"}, set(MOUNT_TYPE_COMPATIBILITY["SYNERGY"]))

    def test_universal_accepts_every_documented_weapon_type(self) -> None:
        self.assertEqual(
            {"BALLISTIC", "ENERGY", "MISSILE", "HYBRID", "COMPOSITE", "SYNERGY", "UNIVERSAL"},
            set(MOUNT_TYPE_COMPATIBILITY["UNIVERSAL"]),
        )

    def test_structural_slot_markers_are_not_weapon_compatibility_categories(self) -> None:
        for marker in ("BUILT_IN", "DECORATIVE", "SYSTEM", "STATION_MODULE", "LAUNCH_BAY"):
            self.assertNotIn(marker, MOUNT_TYPE_COMPATIBILITY)


if __name__ == "__main__":
    unittest.main()
