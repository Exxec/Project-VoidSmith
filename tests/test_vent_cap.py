from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult, Weapon
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.vent_cap import (
    allocate_vents_and_capacitors,
)


class VentCapAllocationTests(unittest.TestCase):
    def test_no_allocation_for_a_source_mod_without_documented_flux_cost(self) -> None:
        hull = Hull("h", "Hull", "fixture_mod", Path("h"), hull_size="FRIGATE", flux_dissipation=100.0, shield_upkeep=0.0)
        allocation = allocate_vents_and_capacitors(hull, [], 10, "BALANCED")
        self.assertEqual((0, 0, 0), (allocation.vents, allocation.capacitors, allocation.op_spent))

    def test_no_allocation_with_no_remaining_op(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", flux_dissipation=100.0, shield_upkeep=0.0)
        allocation = allocate_vents_and_capacitors(hull, [], 0, "BALANCED")
        self.assertEqual((0, 0, 0), (allocation.vents, allocation.capacitors, allocation.op_spent))

    def test_no_allocation_with_incomplete_flux_data(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", flux_dissipation=None, shield_upkeep=0.0)
        weapon = Weapon("w", "W", "core", Path("w"), flux_per_second=50.0)
        allocation = allocate_vents_and_capacitors(hull, [weapon], 10, "BALANCED")
        self.assertEqual((0, 0, 0), (allocation.vents, allocation.capacitors, allocation.op_spent))
        # Missing per-weapon flux data is equally disqualifying.
        hull2 = Hull("h2", "Hull", "core", Path("h"), hull_size="FRIGATE", flux_dissipation=100.0, shield_upkeep=0.0)
        weapon_missing = Weapon("w2", "W2", "core", Path("w"), flux_per_second=None)
        allocation2 = allocate_vents_and_capacitors(hull2, [weapon_missing], 10, "BALANCED")
        self.assertEqual((0, 0, 0), (allocation2.vents, allocation2.capacitors, allocation2.op_spent))

    def test_spends_op_on_vents_to_reach_the_flux_target_then_capacitors(self) -> None:
        # dissipation_per_vent=10, balanced_flux_target=0.75. Weapon load 100/s,
        # hull dissipation 50 -> needs >= 75 to hit target -> 25 more -> 3 vents
        # (ceil(25/10)=3, giving 80, safely at/above target).
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=20, flux_dissipation=50.0, shield_upkeep=0.0)
        weapon = Weapon("w", "W", "core", Path("w"), flux_per_second=100.0)
        allocation = allocate_vents_and_capacitors(hull, [weapon], 10, "BALANCED")
        self.assertEqual(3, allocation.vents)
        self.assertEqual(7, allocation.capacitors)  # remaining 7 OP, FRIGATE max is 10
        self.assertEqual(10, allocation.op_spent)

    def test_vent_allocation_is_capped_at_the_documented_hull_size_maximum(self) -> None:
        # Needs far more than 10 vents to hit target; FRIGATE caps at 10.
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=99, flux_dissipation=0.0, shield_upkeep=0.0)
        weapon = Weapon("w", "W", "core", Path("w"), flux_per_second=10000.0)
        allocation = allocate_vents_and_capacitors(hull, [weapon], 99, "BALANCED")
        self.assertEqual(10, allocation.vents)
        self.assertEqual(10, allocation.capacitors)

    def test_no_sustained_load_still_allocates_capacitors_with_remaining_op(self) -> None:
        hull = Hull("h", "Hull", "core", Path("h"), hull_size="FRIGATE", ordnance_points=10, flux_dissipation=100.0, shield_upkeep=0.0)
        allocation = allocate_vents_and_capacitors(hull, [], 4, "BALANCED")
        self.assertEqual(0, allocation.vents)
        self.assertEqual(4, allocation.capacitors)


class HullmodAdjustedVentCapAllocationTests(unittest.TestCase):
    """baseline_0.10's opt-in `vent_hullmod_adjustment_enabled` gate
    (core/heuristics.py): allocate_vents_and_capacitors sources
    flux_dissipation/shield_upkeep from analysis/flux_stats.py::
    compute_derived_flux_stats (verified hullmod effects) instead of the
    hull's raw base stats, when a hullmod_ids/registry pair is supplied AND
    the caller's heuristic_set carries the gate flag.

    Fixture numbers mirror tests/test_scoring.py's own flux fixture (same
    DESTROYER hull_size, flux_dissipation=100.0, weapon flux_per_second=
    200.0) so the "fewer vents with fluxdistributor installed" effect here
    is directly comparable to that file's already-proven "flux_sustainability
    score saturates at 100.0" effect for the same real-world hullmod.
    """

    def _flux_hullmod_fixture(self):
        hull = Hull("h_flux", "Flux Hull", "core", Path("h"), hull_size="DESTROYER", flux_dissipation=100.0, shield_upkeep=0.0)
        weapon = Weapon("w_flux", "Weapon", "core", Path("w"), flux_per_second=200.0)
        fluxdistributor = Hullmod("fluxdistributor", "Flux Distributor", "core", Path("m"), op_cost_by_hull_size={"DESTROYER": 8})
        safetyoverrides = Hullmod("safetyoverrides", "Safety Overrides", "core", Path("m"), op_cost_by_hull_size={"DESTROYER": 30})
        registry = Registry.from_scan(ScanResult(hulls=[hull], weapons=[weapon], hullmods=[fluxdistributor, safetyoverrides]))
        return registry, hull, [weapon]

    def test_baseline_0_7_0_8_0_9_ignore_hullmod_ids_and_registry(self) -> None:
        # Regression guarantee: passing hullmod_ids/registry under any
        # pre-baseline_0.10 heuristic_set must not change output -- the gate
        # flag is absent there, so allocation stays the raw, unmodified-stat
        # path, byte-for-byte identical to before this task's change.
        for heuristic_set in ("baseline_0.7", "baseline_0.8", "baseline_0.9"):
            with self.subTest(heuristic_set=heuristic_set):
                registry, hull, weapons = self._flux_hullmod_fixture()
                without = allocate_vents_and_capacitors(hull, weapons, 30, "BALANCED", heuristic_set)
                with_mod = allocate_vents_and_capacitors(
                    hull, weapons, 30, "BALANCED", heuristic_set, hullmod_ids=("fluxdistributor",), registry=registry,
                )
                self.assertEqual(5, without.vents)
                self.assertEqual(5, with_mod.vents)
                self.assertNotIn("hullmod-adjusted", with_mod.note)
                self.assertNotIn("hullmod stacking", with_mod.note)

    def test_baseline_0_10_allocates_fewer_vents_with_fluxdistributor_installed(self) -> None:
        # base 100 + DESTROYER's documented +60 = 160; needed = 0.75*200 - 160 = -10 -> 0 vents,
        # vs. 0.75*200 - 100 = 50 -> ceil(50/10) = 5 vents without the hullmod.
        registry, hull, weapons = self._flux_hullmod_fixture()
        without = allocate_vents_and_capacitors(hull, weapons, 30, "BALANCED", "baseline_0.10", hullmod_ids=(), registry=registry)
        with_mod = allocate_vents_and_capacitors(
            hull, weapons, 30, "BALANCED", "baseline_0.10", hullmod_ids=("fluxdistributor",), registry=registry,
        )
        self.assertEqual(5, without.vents)
        self.assertEqual(0, with_mod.vents)
        self.assertIn("flux_dissipation hullmod-adjusted for vent/capacitor allocation: 100.00 -> 160.00 via fluxdistributor", with_mod.note)

    def test_baseline_0_10_without_a_registry_falls_back_to_the_raw_base_value(self) -> None:
        # hullmod_ids alone, with no registry to resolve them against, must
        # not silently adjust anything -- registry is a required half of the
        # opt-in context, not an independent trigger.
        _registry, hull, weapons = self._flux_hullmod_fixture()
        allocation = allocate_vents_and_capacitors(
            hull, weapons, 30, "BALANCED", "baseline_0.10", hullmod_ids=("fluxdistributor",), registry=None,
        )
        self.assertEqual(5, allocation.vents)
        self.assertNotIn("hullmod-adjusted", allocation.note)

    def test_baseline_0_10_stacking_falls_back_to_the_raw_base_value_with_an_explained_ambiguity(self) -> None:
        # fluxdistributor (flat-add) and safetyoverrides (multiply) both
        # target flux_dissipation; compute_derived_flux_stats refuses to
        # fabricate a combined value for that collision, so allocation must
        # fall back to the raw base (documented decision) rather than guess
        # between 160.0 (fluxdistributor alone) and 200.0 (safetyoverrides
        # alone) -- never a silently invented number in between.
        registry, hull, weapons = self._flux_hullmod_fixture()
        allocation = allocate_vents_and_capacitors(
            hull, weapons, 30, "BALANCED", "baseline_0.10",
            hullmod_ids=("fluxdistributor", "safetyoverrides"), registry=registry,
        )
        self.assertEqual(5, allocation.vents)  # same as the raw-base 100.0 case, not 160.0 or 200.0
        self.assertIn("flux_dissipation hullmod stacking is unrepresentable, using unmodified base value", allocation.note)


if __name__ == "__main__":
    unittest.main()
