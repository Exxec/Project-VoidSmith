from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult
from starsector_variant_generator.core.registry import Registry
from starsector_variant_generator.generation.hullmods import select_hullmods

SOURCE = Path("fixture")


class HullmodSelectionTests(unittest.TestCase):
    def _hull(self, **overrides) -> Hull:
        return Hull("hull", "Hull", "core", SOURCE, hull_size="FRIGATE", **overrides)

    def test_cheapest_eligible_hullmods_are_selected_within_budget(self) -> None:
        hull = self._hull()
        cheap = Hullmod("cheap", "Cheap", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 2})
        pricey = Hullmod("pricey", "Pricey", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 8})
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[cheap, pricey]))
        selection = select_hullmods(hull, registry, remaining_op=5)
        self.assertEqual(("cheap",), selection.hullmod_ids)
        self.assertEqual(2, selection.op_spent)

    def test_hidden_hullmods_are_never_selected(self) -> None:
        hull = self._hull()
        hidden = Hullmod("hidden_mod", "Hidden", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1}, hidden=True)
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[hidden]))
        selection = select_hullmods(hull, registry, remaining_op=10)
        self.assertEqual((), selection.hullmod_ids)

    def test_built_in_hullmods_are_never_reselected(self) -> None:
        hull = self._hull(built_in_hullmods=("already_built_in",))
        mod = Hullmod("already_built_in", "Already", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[mod]))
        selection = select_hullmods(hull, registry, remaining_op=10)
        self.assertEqual((), selection.hullmod_ids)

    def test_preferred_hullmods_are_prioritized_over_cheaper_alternatives(self) -> None:
        hull = self._hull()
        cheap = Hullmod("cheap", "Cheap", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 2})
        native = Hullmod("native", "Native", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 4})
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[cheap, native]))
        selection = select_hullmods(hull, registry, remaining_op=4, preferred_hullmod_ids={"native"})
        self.assertEqual(("native",), selection.hullmod_ids)

    def test_denied_and_disallowed_hullmods_are_excluded(self) -> None:
        hull = self._hull()
        denied = Hullmod("denied", "Denied", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        not_allowed = Hullmod("not_allowed", "NotAllowed", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        allowed = Hullmod("allowed", "Allowed", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1})
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[denied, not_allowed, allowed]))
        selection = select_hullmods(hull, registry, remaining_op=10, allowed_hullmod_ids={"allowed"}, denied_hullmod_ids={"denied"})
        self.assertEqual(("allowed",), selection.hullmod_ids)

    def test_priority_tag_prefers_matching_category_over_cheaper_alternatives(self) -> None:
        hull = self._hull()
        cheap_other = Hullmod("cheap_other", "CheapOther", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1}, raw={"uiTags": "Weapons"})
        defensive = Hullmod("defensive", "Defensive", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 3}, raw={"uiTags": "Defenses"})
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[cheap_other, defensive]))
        selection = select_hullmods(hull, registry, remaining_op=3, priority_tag="Defenses")
        self.assertEqual(("defensive",), selection.hullmod_ids)

    def test_defense_priority_prefers_an_applicable_verified_effect_without_a_ui_tag(self) -> None:
        # This checks the adapter/derived-state path, not a name or uiTags
        # heuristic. heavyarmor is a documented core effect; the competing
        # hullmod only claims the generic Defenses category.
        hull = self._hull(raw={"armor rating": 300})
        tagged = Hullmod("tagged", "Tagged", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1}, raw={"uiTags": "Defenses"})
        heavy_armor = Hullmod("heavyarmor", "Heavy Armor", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 2})
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=[tagged, heavy_armor]))
        selection = select_hullmods(hull, registry, remaining_op=2, max_hullmods=1, priority_tag="Defenses")
        self.assertEqual(("heavyarmor",), selection.hullmod_ids)

    def test_selection_is_capped_at_max_hullmods_even_with_ample_op(self) -> None:
        hull = self._hull(ordnance_points=99)
        mods = [Hullmod(f"m{i}", f"M{i}", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1}) for i in range(10)]
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=mods))
        selection = select_hullmods(hull, registry, remaining_op=99)
        self.assertEqual(2, len(selection.hullmod_ids))

    def test_logistics_tagged_hullmods_are_capped_at_the_documented_maximum(self) -> None:
        # max_hullmods raised above the logistics cap so this isolates the
        # logistics-specific rule, not the general per-candidate cap.
        hull = self._hull()
        logistics_mods = [
            Hullmod(f"log{i}", f"Log{i}", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 1}, raw={"uiTags": "Logistics, Requires Dock"})
            for i in range(4)
        ]
        registry = Registry.from_scan(ScanResult(hulls=[hull], hullmods=logistics_mods))
        selection = select_hullmods(hull, registry, remaining_op=10, max_hullmods=10)
        self.assertEqual(2, len(selection.hullmod_ids))


if __name__ == "__main__":
    unittest.main()
