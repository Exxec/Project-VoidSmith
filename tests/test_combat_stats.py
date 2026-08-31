from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.combat_stats import (
    compute_derived_defense_stats,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def registry_with(*, hulls: tuple[Hull, ...] = (), hullmods: tuple[Hullmod, ...] = ()) -> Registry:
    return Registry.from_scan(ScanResult(hulls=list(hulls), hullmods=list(hullmods)))


class DerivedDefenseStatsTests(unittest.TestCase):
    def test_heavyarmor_applies_flat_bonus_by_hull_size(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300"})
        derived = compute_derived_defense_stats(hull, ["heavyarmor"], registry_with())
        self.assertEqual(300.0, derived.armor_rating_base)
        self.assertEqual(450.0, derived.effective_armor_rating)
        self.assertEqual(("heavyarmor",), derived.applied_effect_hullmod_ids)

    def test_heavyarmor_bonus_differs_by_hull_size(self) -> None:
        capital = Hull("h", "Hull", "core", SOURCE, hull_size="CAPITAL_SHIP", raw={"armor rating": "1750"})
        derived = compute_derived_defense_stats(capital, ["heavyarmor"], registry_with())
        self.assertEqual(2250.0, derived.effective_armor_rating)

    def test_armoredweapons_applies_percent_bonus_to_armor(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300"})
        derived = compute_derived_defense_stats(hull, ["armoredweapons"], registry_with())
        self.assertEqual(330.0, derived.effective_armor_rating)

    def test_reinforcedhull_applies_percent_bonus_to_hull_hp(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"hitpoints": "1750"})
        derived = compute_derived_defense_stats(hull, ["reinforcedhull"], registry_with())
        self.assertEqual(1750.0, derived.hull_hp_base)
        self.assertEqual(2450.0, derived.effective_hull_hp)
        self.assertEqual(("reinforcedhull",), derived.applied_effect_hullmod_ids)

    def test_blast_doors_applies_percent_bonus_to_hull_hp(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={"hitpoints": "5000"})
        derived = compute_derived_defense_stats(hull, ["blast_doors"], registry_with())
        self.assertEqual(6000.0, derived.effective_hull_hp)

    def test_insulated_engine_applies_only_its_verified_hull_integrity_bonus(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"hitpoints": "1750"})
        derived = compute_derived_defense_stats(hull, ["insulatedengine"], registry_with())
        self.assertEqual(1925.0, derived.effective_hull_hp)
        self.assertEqual(("insulatedengine",), derived.applied_effect_hullmod_ids)

    def test_unverified_hullmod_is_reported_not_silently_applied(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300"})
        derived = compute_derived_defense_stats(hull, ["some_unresearched_hullmod"], registry_with())
        self.assertEqual(300.0, derived.effective_armor_rating)
        self.assertEqual((), derived.applied_effect_hullmod_ids)
        self.assertEqual(("some_unresearched_hullmod",), derived.unverified_hullmod_ids)

    def test_missing_base_stat_leaves_effective_value_none_not_zero(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={})
        derived = compute_derived_defense_stats(hull, ["heavyarmor"], registry_with())
        self.assertIsNone(derived.armor_rating_base)
        self.assertIsNone(derived.effective_armor_rating)
        self.assertEqual(("heavyarmor",), derived.unverified_hullmod_ids)

    def test_undocumented_hull_size_is_left_unverified(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FIGHTER", raw={"armor rating": "10"})
        derived = compute_derived_defense_stats(hull, ["heavyarmor"], registry_with())
        self.assertEqual(10.0, derived.effective_armor_rating)
        self.assertEqual(("heavyarmor",), derived.unverified_hullmod_ids)

    def test_two_hullmods_on_the_same_stat_do_not_combine_into_one_value(self) -> None:
        # Both reinforcedhull (+40%) and blast_doors (+20%) target hull_hp --
        # combined stacking behavior is undocumented, so no single effective
        # value should be fabricated; each contribution stays individually
        # visible instead.
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"hitpoints": "1750"})
        derived = compute_derived_defense_stats(hull, ["reinforcedhull", "blast_doors"], registry_with())
        self.assertIsNone(derived.effective_hull_hp)
        self.assertEqual(1, len(derived.stacking_notes))
        self.assertIn("hull_hp", derived.stacking_notes[0])
        self.assertEqual(2, len(derived.applied_effects))
        gains = {effect.hullmod_id: effect.gain for effect in derived.applied_effects}
        self.assertEqual(700.0, gains["reinforcedhull"])
        self.assertEqual(350.0, gains["blast_doors"])

    def test_two_hullmods_on_different_stats_both_apply_independently(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300", "hitpoints": "1750"})
        derived = compute_derived_defense_stats(hull, ["heavyarmor", "reinforcedhull"], registry_with())
        self.assertEqual(450.0, derived.effective_armor_rating)
        self.assertEqual(2450.0, derived.effective_hull_hp)
        self.assertEqual((), derived.stacking_notes)

    def test_efficiency_is_gain_per_op_spent(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300"})
        heavyarmor = Hullmod("heavyarmor", "Heavy Armor", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 8})
        derived = compute_derived_defense_stats(hull, ["heavyarmor"], registry_with(hullmods=(heavyarmor,)))
        effect = derived.applied_effects[0]
        self.assertEqual(150.0, effect.gain)
        self.assertEqual(8, effect.op_cost)
        self.assertEqual(18.75, effect.efficiency)

    def test_efficiency_is_none_when_op_cost_is_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300"})
        derived = compute_derived_defense_stats(hull, ["heavyarmor"], registry_with())
        self.assertIsNone(derived.applied_effects[0].efficiency)

    def test_skin_derived_hull_falls_back_to_base_hulls_raw_csv_row(self) -> None:
        base = Hull("base_hull", "Base", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300", "hitpoints": "1750"})
        skin = Hull("skin_hull", "Skin", "core", SOURCE, hull_size="FRIGATE",
                    raw={"skin_data": {}, "base_hull_id": "base_hull", "base_hull_source_mod": "core"})
        registry = registry_with(hulls=(base, skin))
        derived = compute_derived_defense_stats(skin, ["heavyarmor"], registry)
        self.assertEqual(300.0, derived.armor_rating_base)
        self.assertEqual(450.0, derived.effective_armor_rating)

    def test_skin_with_unresolvable_base_hull_leaves_stat_unavailable(self) -> None:
        skin = Hull("skin_hull", "Skin", "core", SOURCE, hull_size="FRIGATE",
                    raw={"skin_data": {}, "base_hull_id": "missing_base", "base_hull_source_mod": "core"})
        derived = compute_derived_defense_stats(skin, ["heavyarmor"], registry_with())
        self.assertIsNone(derived.armor_rating_base)
        self.assertEqual(("heavyarmor",), derived.unverified_hullmod_ids)

    def test_applied_defense_effects_carry_the_unified_adapter_modeled_evidence_class(self) -> None:
        """ROADMAP.md Phase 29 (Evidence/Provenance Unification): always
        sourced from a verified adapters.defense_hullmod_effects table
        entry, so this must always report `ADAPTER_MODELED`."""
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"armor rating": "300"})
        derived = compute_derived_defense_stats(hull, ["heavyarmor"], registry_with())
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, derived.applied_effects[0].evidence_class)


if __name__ == "__main__":
    unittest.main()
