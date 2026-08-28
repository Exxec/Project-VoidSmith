from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.flux_stats import compute_derived_flux_stats
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult
from starsector_variant_generator.core.registry import Registry


SOURCE = Path("fixture")


def registry_with(*, hullmods: tuple[Hullmod, ...] = ()) -> Registry:
    return Registry.from_scan(ScanResult(hullmods=list(hullmods)))


class DerivedFluxStatsTests(unittest.TestCase):
    def test_fluxdistributor_applies_flat_bonus_by_hull_size(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", flux_dissipation=400.0)
        derived = compute_derived_flux_stats(hull, ["fluxdistributor"], registry_with())
        self.assertEqual(400.0, derived.flux_dissipation_base)
        self.assertEqual(460.0, derived.effective_flux_dissipation)
        self.assertEqual(("fluxdistributor",), derived.applied_effect_hullmod_ids)
        effect = derived.applied_effects[0]
        self.assertEqual("flat_add", effect.operation)
        self.assertEqual(60.0, effect.delta)

    def test_safetyoverrides_multiplies_flux_dissipation(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0)
        derived = compute_derived_flux_stats(hull, ["safetyoverrides"], registry_with())
        self.assertEqual(200.0, derived.effective_flux_dissipation)
        effect = derived.applied_effects[0]
        self.assertEqual("multiply", effect.operation)
        self.assertEqual(200.0, effect.resulting_value_alone)
        self.assertEqual(100.0, effect.delta)

    def test_safetyoverrides_is_not_applied_on_capital_ships(self) -> None:
        # The hullmod's own desc text: "Can not be installed on civilian or
        # capital ships" -- excluded_hull_sizes gates this so a variant that
        # nonetheless carries it on a capital hull never gets a fabricated
        # x2 bonus.
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CAPITAL_SHIP", flux_dissipation=1000.0)
        derived = compute_derived_flux_stats(hull, ["safetyoverrides"], registry_with())
        self.assertEqual(1000.0, derived.effective_flux_dissipation)
        self.assertEqual((), derived.applied_effect_hullmod_ids)
        self.assertEqual(("safetyoverrides",), derived.unverified_hullmod_ids)

    def test_stabilizedshieldemitter_reduces_shield_upkeep(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CRUISER", shield_upkeep=0.8)
        derived = compute_derived_flux_stats(hull, ["stabilizedshieldemitter"], registry_with())
        self.assertEqual(0.8, derived.shield_upkeep_base)
        self.assertEqual(0.4, derived.effective_shield_upkeep)
        effect = derived.applied_effects[0]
        self.assertEqual("percent_reduce", effect.operation)
        self.assertEqual(-0.4, effect.delta)

    def test_unverified_hullmod_is_reported_not_silently_applied(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0)
        derived = compute_derived_flux_stats(hull, ["some_unresearched_hullmod"], registry_with())
        self.assertEqual(100.0, derived.effective_flux_dissipation)
        self.assertEqual((), derived.applied_effect_hullmod_ids)
        self.assertEqual(("some_unresearched_hullmod",), derived.unverified_hullmod_ids)

    def test_missing_base_stat_leaves_effective_value_none_not_zero(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE")
        derived = compute_derived_flux_stats(hull, ["fluxdistributor"], registry_with())
        self.assertIsNone(derived.flux_dissipation_base)
        self.assertIsNone(derived.effective_flux_dissipation)
        self.assertEqual(("fluxdistributor",), derived.unverified_hullmod_ids)

    def test_two_hullmods_on_different_stats_both_apply_independently(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0, shield_upkeep=0.8)
        derived = compute_derived_flux_stats(hull, ["fluxdistributor", "stabilizedshieldemitter"], registry_with())
        self.assertEqual(130.0, derived.effective_flux_dissipation)
        self.assertEqual(0.4, derived.effective_shield_upkeep)
        self.assertEqual((), derived.stacking_notes)

    def test_fluxdistributor_and_safetyoverrides_stack_on_flux_dissipation_without_a_fabricated_combined_value(self) -> None:
        # Both target flux_dissipation via different operations (flat-add vs.
        # x2 multiply); vanilla does not document how they combine, so no
        # single effective value should be produced -- each contribution
        # must remain individually visible.
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0)
        derived = compute_derived_flux_stats(hull, ["fluxdistributor", "safetyoverrides"], registry_with())
        self.assertIsNone(derived.effective_flux_dissipation)
        self.assertEqual(1, len(derived.stacking_notes))
        self.assertIn("flux_dissipation", derived.stacking_notes[0])
        self.assertEqual(2, len(derived.applied_effects))
        by_id = {effect.hullmod_id: effect for effect in derived.applied_effects}
        self.assertEqual("flat_add", by_id["fluxdistributor"].operation)
        self.assertEqual(130.0, by_id["fluxdistributor"].resulting_value_alone)
        self.assertEqual("multiply", by_id["safetyoverrides"].operation)
        self.assertEqual(200.0, by_id["safetyoverrides"].resulting_value_alone)

    def test_efficiency_is_delta_per_op_spent(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0)
        mod = Hullmod("fluxdistributor", "Flux Distributor", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 4})
        derived = compute_derived_flux_stats(hull, ["fluxdistributor"], registry_with(hullmods=(mod,)))
        effect = derived.applied_effects[0]
        self.assertEqual(30.0, effect.delta)
        self.assertEqual(4, effect.op_cost)
        self.assertEqual(7.5, effect.efficiency)

    def test_efficiency_is_none_when_op_cost_is_unknown(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0)
        derived = compute_derived_flux_stats(hull, ["fluxdistributor"], registry_with())
        self.assertIsNone(derived.applied_effects[0].efficiency)

    def test_applied_flux_effects_carry_the_unified_adapter_modeled_evidence_class(self) -> None:
        """ROADMAP.md Phase 29 (Evidence/Provenance Unification): always
        sourced from a verified adapters.flux_hullmod_effects table entry,
        so this must always report `ADAPTER_MODELED`, regardless of which
        of the three real operation shapes (flat_add/multiply/percent_reduce)
        produced it."""
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", flux_dissipation=100.0)
        derived = compute_derived_flux_stats(hull, ["fluxdistributor"], registry_with())
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, derived.applied_effects[0].evidence_class)


if __name__ == "__main__":
    unittest.main()
