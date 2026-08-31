from __future__ import annotations

import unittest
from pathlib import Path

from starsector_variant_generator.analysis.mobility_stats import (
    compute_derived_mobility_stats,
)
from starsector_variant_generator.core.evidence import EvidenceClass
from starsector_variant_generator.core.models import Hull, Hullmod, ScanResult
from starsector_variant_generator.core.registry import Registry

SOURCE = Path("fixture")


def registry_with(*hullmods: Hullmod) -> Registry:
    return Registry.from_scan(ScanResult(hullmods=list(hullmods)))


class DerivedMobilityStatsTests(unittest.TestCase):
    def test_unstable_injector_applies_documented_size_specific_speed(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={"max speed": "60"})
        derived = compute_derived_mobility_stats(hull, ("unstable_injector",), registry_with())
        self.assertEqual(80.0, derived.effective_values["max_speed"])
        self.assertEqual(("unstable_injector",), derived.applied_effect_hullmod_ids)

    def test_auxiliary_thrusters_apply_independent_documented_maneuvering_stats(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"acceleration": "100", "deceleration": "80", "max turn rate": "60", "turn acceleration": "40"})
        derived = compute_derived_mobility_stats(hull, ("auxiliarythrusters",), registry_with())
        self.assertEqual(200.0, derived.effective_values["acceleration"])
        self.assertEqual(120.0, derived.effective_values["deceleration"])
        self.assertEqual(90.0, derived.effective_values["max_turn_rate"])
        self.assertEqual(80.0, derived.effective_values["turn_acceleration"])

    def test_unknown_or_unsupported_effect_is_reported_not_applied(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="CAPITAL_SHIP", raw={"max speed": "40"})
        derived = compute_derived_mobility_stats(hull, ("safetyoverrides", "unknown_mod"), registry_with())
        self.assertEqual(40.0, derived.effective_values["max_speed"])
        self.assertEqual(("safetyoverrides", "unknown_mod"), derived.unverified_hullmod_ids)

    def test_same_stat_effects_do_not_assume_a_stacking_rule(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"max speed": "60"})
        derived = compute_derived_mobility_stats(hull, ("unstable_injector", "safetyoverrides"), registry_with())
        self.assertIsNone(derived.effective_values["max_speed"])
        self.assertEqual(1, len(derived.stacking_notes))

    def test_effect_efficiency_uses_real_op_cost_when_available(self) -> None:
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="FRIGATE", raw={"max speed": "60"})
        mod = Hullmod("unstable_injector", "Unstable Injector", "core", SOURCE, op_cost_by_hull_size={"FRIGATE": 5})
        effect = compute_derived_mobility_stats(hull, ("unstable_injector",), registry_with(mod)).applied_effects[0]
        self.assertEqual(25.0, effect.gain)
        self.assertEqual(5.0, effect.efficiency)

    def test_applied_mobility_effects_carry_the_unified_adapter_modeled_evidence_class(self) -> None:
        """ROADMAP.md Phase 29 (Evidence/Provenance Unification): always
        sourced from a verified adapters.mobility_hullmod_effects table
        entry, so this must always report `ADAPTER_MODELED`."""
        hull = Hull("h", "Hull", "core", SOURCE, hull_size="DESTROYER", raw={"max speed": "60"})
        derived = compute_derived_mobility_stats(hull, ("unstable_injector",), registry_with())
        self.assertEqual(EvidenceClass.ADAPTER_MODELED, derived.applied_effects[0].evidence_class)


if __name__ == "__main__":
    unittest.main()
