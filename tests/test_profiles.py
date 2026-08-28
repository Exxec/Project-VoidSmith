from __future__ import annotations

import unittest

from starsector_variant_generator.profiles.catalog import available_profiles, get_profile


class ProfileCatalogTests(unittest.TestCase):
    def test_catalog_has_seven_explicit_deterministic_profiles(self) -> None:
        self.assertEqual(
            {"LINE_BRAWLER", "LINE_ARTILLERY", "FAST_STRIKE", "TANK", "MISSILE_SUPPORT", "CARRIER_SUPPORT", "PD_ESCORT"},
            {profile.identifier for profile in available_profiles()},
        )
        self.assertEqual("LONG_RANGE", get_profile("LINE_ARTILLERY").role_signal)
        self.assertEqual("Defenses", get_profile("TANK").hullmod_priority_tag)
        self.assertEqual("Fighters", get_profile("CARRIER_SUPPORT").hullmod_priority_tag)
        self.assertEqual("PD_FIRST", get_profile("PD_ESCORT").weapon_priority)

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown profile"):
            get_profile("INVENTED_PROFILE")


if __name__ == "__main__":
    unittest.main()
