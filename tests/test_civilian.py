from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.civilian import (
    compute_derived_civilian_stats,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def registry_with(*hullmods: Hullmod) -> Registry:
    return Registry.from_scan(ScanResult(hullmods=list(hullmods)))


class DerivedCivilianStatsTests(unittest.TestCase):
    def test_flat_bonus_wins_when_higher_than_percent(self) -> None:
        # Frigate: flat +30 vs 30% of 40 (=12) -> flat wins.
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds"], registry_with(), is_civilian=False)
        self.assertEqual(70.0, derived.cargo_capacity)
        self.assertEqual(("expanded_cargo_holds",), derived.applied_effect_hullmod_ids)

    def test_percent_bonus_wins_when_higher_than_flat(self) -> None:
        # Frigate: flat +30 vs 30% of 900 (=270) -> percent wins.
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=900.0)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds"], registry_with(), is_civilian=False)
        self.assertEqual(1170.0, derived.cargo_capacity)

    def test_flat_only_effect_applies_uniformly_across_hull_sizes(self) -> None:
        frigate = Hull("h1", "H1", "core", SOURCE, hull_size="FRIGATE", max_burn=8.0)
        capital = Hull("h2", "H2", "core", SOURCE, hull_size="CAPITAL_SHIP", max_burn=6.0)
        self.assertEqual(10.0, compute_derived_civilian_stats(frigate, ["augmentedengines"], registry_with(), is_civilian=False).max_burn)
        self.assertEqual(8.0, compute_derived_civilian_stats(capital, ["augmentedengines"], registry_with(), is_civilian=False).max_burn)

    def test_unverified_hullmod_is_reported_not_silently_applied(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0)
        derived = compute_derived_civilian_stats(hull, ["some_unresearched_hullmod"], registry_with(), is_civilian=False)
        self.assertEqual(40.0, derived.cargo_capacity)
        self.assertEqual((), derived.applied_effect_hullmod_ids)
        self.assertEqual(("some_unresearched_hullmod",), derived.unverified_hullmod_ids)

    def test_civilian_maintenance_penalty_is_a_note_not_a_computed_number(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0, fuel_capacity=25.0)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds", "auxiliary_fuel_tanks"], registry_with(), is_civilian=True)
        self.assertEqual(2, len(derived.civilian_maintenance_penalty_notes))
        # Not civilian: no penalty notes even with the same hullmods applied.
        not_civilian = compute_derived_civilian_stats(hull, ["expanded_cargo_holds"], registry_with(), is_civilian=False)
        self.assertEqual((), not_civilian.civilian_maintenance_penalty_notes)

    def test_no_documented_bonus_for_an_undocumented_hull_size_is_left_unverified(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FIGHTER", cargo_capacity=10.0)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds"], registry_with(), is_civilian=False)
        self.assertEqual(10.0, derived.cargo_capacity)
        self.assertEqual(("expanded_cargo_holds",), derived.unverified_hullmod_ids)

    def test_efficiency_is_gain_per_op_spent_per_hullmods_civilian_and_refit_section_9(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0)
        cargo_mod = Hullmod("expanded_cargo_holds", "Expanded Cargo Holds", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 5})
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds"], registry_with(cargo_mod), is_civilian=False)
        effect = derived.applied_effects[0]
        self.assertEqual(30.0, effect.gain)
        self.assertEqual(5, effect.op_cost)
        self.assertEqual(6.0, effect.efficiency)

    def test_efficiency_is_none_when_op_cost_is_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds"], registry_with(), is_civilian=False)
        self.assertIsNone(derived.applied_effects[0].efficiency)

    def test_efficiency_overhaul_reduces_supplies_and_min_crew_by_20_percent(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", supplies_per_month=10.0, crew_min=5)
        derived = compute_derived_civilian_stats(hull, ["efficiency_overhaul"], registry_with(), is_civilian=False)
        self.assertEqual(8.0, derived.supplies_per_month)
        self.assertEqual(4.0, derived.crew_min)
        self.assertEqual(("efficiency_overhaul",), derived.applied_effect_hullmod_ids)
        self.assertEqual(2, len(derived.applied_reduction_effects))

    def test_efficiency_overhaul_does_not_touch_cargo_or_fuel(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=100.0, fuel_capacity=50.0, supplies_per_month=10.0, crew_min=5)
        derived = compute_derived_civilian_stats(hull, ["efficiency_overhaul"], registry_with(), is_civilian=False)
        self.assertEqual(100.0, derived.cargo_capacity)
        self.assertEqual(50.0, derived.fuel_capacity)

    def test_efficiency_overhaul_is_unverified_when_neither_target_stat_is_known(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        derived = compute_derived_civilian_stats(hull, ["efficiency_overhaul"], registry_with(), is_civilian=False)
        self.assertEqual(("efficiency_overhaul",), derived.unverified_hullmod_ids)
        self.assertEqual((), derived.applied_reduction_effects)

    def test_militarized_subsystems_applies_two_independent_effects_from_one_hullmod(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", max_burn=8.0, crew_min=10)
        derived = compute_derived_civilian_stats(hull, ["militarized_subsystems"], registry_with(), is_civilian=False)
        self.assertEqual(9.0, derived.max_burn)
        self.assertEqual(20.0, derived.crew_min)
        self.assertEqual(("militarized_subsystems",), derived.applied_effect_hullmod_ids)
        self.assertEqual(2, len(derived.applied_effects))

    def test_militarized_subsystems_is_partially_unverified_when_only_one_stat_is_known(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", max_burn=8.0)
        derived = compute_derived_civilian_stats(hull, ["militarized_subsystems"], registry_with(), is_civilian=False)
        self.assertEqual(9.0, derived.max_burn)
        self.assertEqual(1, len(derived.applied_effects))
        self.assertEqual((), derived.unverified_hullmod_ids)

    def test_reduction_and_increase_effects_can_both_apply_from_one_loadout(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0, supplies_per_month=10.0, crew_min=5)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds", "efficiency_overhaul"], registry_with(), is_civilian=False)
        self.assertEqual(70.0, derived.cargo_capacity)
        self.assertEqual(8.0, derived.supplies_per_month)
        self.assertEqual(1, len(derived.applied_effects))
        self.assertEqual(2, len(derived.applied_reduction_effects))

    def test_applied_effects_carry_the_unified_adapter_modeled_evidence_class(self) -> None:
        """ROADMAP.md Phase 29 (Evidence/Provenance Unification): every
        AppliedLogisticsEffect/AppliedReductionEffect is, by construction,
        sourced from a verified adapters.logistics_hullmod_effects /
        adapters.efficiency_hullmod_effects table entry (AGENTS.md's
        adapter-layer ladder tier 6) -- so both must always report the
        shared vocabulary's `ADAPTER_MODELED` class, not left informal."""
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", cargo_capacity=40.0, supplies_per_month=10.0, crew_min=5)
        derived = compute_derived_civilian_stats(hull, ["expanded_cargo_holds", "efficiency_overhaul"], registry_with(), is_civilian=False)
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, derived.applied_effects[0].evidence_class)
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, derived.applied_reduction_effects[0].evidence_class)


if __name__ == "__main__":
    unittest.main()
