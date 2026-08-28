from __future__ import annotations

import unittest

from starsector_variant_generator.profiles.modes import UserMode, resolve_mode


class ModeTests(unittest.TestCase):
    def test_modes_are_presets_not_separate_engines(self) -> None:
        beginner = resolve_mode(UserMode.BEGINNER, "LINE_ARTILLERY")
        advanced = resolve_mode(UserMode.ADVANCED, "LINE_ARTILLERY")
        self.assertEqual("LINE_ARTILLERY", beginner.profile_id)
        self.assertEqual("FACTION_PLUS", beginner.faction_mode)
        self.assertEqual("UNRESTRICTED", advanced.faction_mode)

    def test_flux_mode_escalates_from_beginner_to_advanced(self) -> None:
        self.assertEqual("SAFE", resolve_mode(UserMode.BEGINNER).flux_mode)
        self.assertEqual("BALANCED", resolve_mode(UserMode.GUIDED).flux_mode)
        self.assertEqual("AGGRESSIVE", resolve_mode(UserMode.ADVANCED).flux_mode)


if __name__ == "__main__":
    unittest.main()
