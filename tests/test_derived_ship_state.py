from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.derived_ship_state import derive_ship_state
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Variant
from starsector_variant_generator.core.registry import Registry


class DerivedShipStateTests(unittest.TestCase):
    def test_aggregate_preserves_verified_and_unknown_effect_boundaries(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", raw={"armor rating":"300", "max speed":"60"})
        variant = Variant("v", "V", "core", Path("v"), hull_id="h", hullmods=("heavyarmor", "unknown"))
        state = derive_ship_state(variant, hull, Registry.from_scan(ScanResult(hulls=[hull], variants=[variant], hullmods=[Hullmod("heavyarmor", "HA", "core", Path("m"), op_cost_by_hull_size={"FRIGATE":8})])))
        self.assertEqual(450.0, state.defense.effective_armor_rating)
        self.assertEqual(("unknown",), state.unapplied_unknown_hullmod_ids)
        self.assertEqual(0.5, state.confidence_summary)

if __name__ == "__main__": unittest.main()
