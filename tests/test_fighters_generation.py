from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import FighterWing, Hull, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.fighters import select_fighter_wings

SOURCE = Path("fixture")


class FighterWingSelectionTests(unittest.TestCase):
    def test_no_selection_without_documented_bay_capacity(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE)
        wing = FighterWing("wing", "Wing", "core", SOURCE, op_cost=5)
        registry = Registry.from_scan(ScanResult(hulls=[hull], fighters=[wing]))
        selection = select_fighter_wings(hull, registry, remaining_op=20)
        self.assertEqual((), selection.wing_ids)

    def test_fills_bays_up_to_capacity_and_op_budget(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, fighter_bays=2)
        cheap = FighterWing("cheap", "Cheap", "core", SOURCE, op_cost=4)
        pricey = FighterWing("pricey", "Pricey", "core", SOURCE, op_cost=10)
        registry = Registry.from_scan(ScanResult(hulls=[hull], fighters=[cheap, pricey]))
        selection = select_fighter_wings(hull, registry, remaining_op=6)
        self.assertEqual(("cheap",), selection.wing_ids)
        self.assertEqual(4, selection.op_spent)

    def test_selection_never_exceeds_documented_bay_count_even_with_ample_op(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, fighter_bays=1)
        wings = [FighterWing(f"w{i}", f"W{i}", "core", SOURCE, op_cost=1) for i in range(5)]
        registry = Registry.from_scan(ScanResult(hulls=[hull], fighters=wings))
        selection = select_fighter_wings(hull, registry, remaining_op=99)
        self.assertEqual(1, len(selection.wing_ids))

    def test_built_in_wings_are_never_reselected(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, fighter_bays=1, built_in_fighter_wings=("already_built_in",))
        wing = FighterWing("already_built_in", "Already", "core", SOURCE, op_cost=1)
        registry = Registry.from_scan(ScanResult(hulls=[hull], fighters=[wing]))
        selection = select_fighter_wings(hull, registry, remaining_op=10)
        self.assertEqual((), selection.wing_ids)

    def test_preferred_wings_are_prioritized_over_cheaper_alternatives(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, fighter_bays=1)
        cheap = FighterWing("cheap", "Cheap", "core", SOURCE, op_cost=2)
        native = FighterWing("native", "Native", "core", SOURCE, op_cost=4)
        registry = Registry.from_scan(ScanResult(hulls=[hull], fighters=[cheap, native]))
        selection = select_fighter_wings(hull, registry, remaining_op=4, preferred_wing_ids={"native"})
        self.assertEqual(("native",), selection.wing_ids)


if __name__ == "__main__":
    unittest.main()
